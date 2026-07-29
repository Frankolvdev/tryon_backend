from __future__ import annotations

import time
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.services.beam_engine.beam_config import BeamSyncConfig
from app.services.beam_engine.beam_models import BeamModelFile, BeamSyncSummary
from app.services.beam_engine.beam_multipart_client import BeamMultipartClient
from app.services.beam_engine.beam_progress_service import BeamProgressService
from app.services.beam_engine.beam_volume_service import BeamVolumeService

Notify = Callable[..., None]


class BeamModelSyncService:
    @staticmethod
    def _items(manifest_models: list[dict[str, Any]]) -> list[BeamModelFile]:
        items: list[BeamModelFile] = []
        seen: set[tuple[str, str]] = set()
        for raw in manifest_models:
            if not raw.get("found", True):
                continue
            source = Path(str(raw.get("source_path") or "")).resolve()
            relative = str(raw.get("target_path") or raw.get("relative_path") or source.name).replace("\\", "/")
            if relative.startswith("models/"):
                relative = relative[7:]
            relative = str(PurePosixPath(relative.strip("/")))
            key = (str(source).casefold(), relative.casefold())
            if not source.is_file() or key in seen:
                continue
            seen.add(key)
            items.append(
                BeamModelFile(
                    source,
                    relative,
                    relative.split("/", 1)[0],
                    source.stat().st_size,
                    raw.get("sha256"),
                    dict(raw),
                )
            )
        return items

    @classmethod
    def sync(
        cls,
        db: Session,
        *,
        manifest_models: list[dict[str, Any]],
        remote_prefix: str,
        skip_identical: bool,
        notify: Notify,
    ) -> dict[str, Any]:
        config = BeamSyncConfig.load(db)
        items = cls._items(manifest_models)
        summary = BeamSyncSummary()
        total_bytes = sum(item.size_bytes for item in items)
        completed_bytes = 0
        uploaded_bytes = 0
        started = time.perf_counter()

        notify(
            "beam-preparing",
            1,
            f"Beam: {len(items)} archivos del runtime listos para verificar.",
            {
                "status": "PREPARING",
                "files_total": len(items),
                "bytes_total": total_bytes,
                "skip_identical": skip_identical,
            },
        )

        for index, item in enumerate(items, 1):
            if BeamProgressService.is_cancelled():
                raise RuntimeError("Sincronización Beam cancelada por el usuario.")

            remote_path = "/".join(
                part for part in (
                    remote_prefix.strip("/\\").replace("\\", "/"),
                    item.relative_path,
                ) if part
            )
            destination = BeamVolumeService.remote_uri(config.volume_name, remote_path)

            notify(
                "beam-checking",
                max(1, min(99, int(100 * completed_bytes / max(1, total_bytes)))),
                f"Verificando {item.relative_path} — archivo {index} de {len(items)}",
                {
                    "status": "CHECKING",
                    "file_name": item.source.name,
                    "relative_path": item.relative_path,
                    "remote_path": remote_path,
                    "category": item.category,
                    "file_index": index,
                    "files_total": len(items),
                    "file_bytes_total": item.size_bytes,
                    "bytes_completed": completed_bytes,
                    "bytes_uploaded": uploaded_bytes,
                    "bytes_total": total_bytes,
                },
            )

            identical_metadata = (
                BeamVolumeService.identical_metadata(config, remote_path, item.size_bytes)
                if skip_identical
                else None
            )
            if identical_metadata is not None:
                completed_bytes += item.size_bytes
                summary.skipped += 1
                global_progress = round(100 * completed_bytes / max(1, total_bytes), 2)
                notify(
                    "beam-skipped",
                    min(99, max(1, int(global_progress))),
                    f"SKIPPED idéntico: {item.relative_path} — archivo {index} de {len(items)}",
                    {
                        "status": "SKIPPED",
                        "skip_reason": "same-size-remote-file",
                        "remote_metadata": identical_metadata,
                        "remote_size_bytes": int(identical_metadata.get("size_bytes") or 0),
                        "remote_metadata_source": identical_metadata.get("source"),
                        "file_name": item.source.name,
                        "relative_path": item.relative_path,
                        "remote_path": remote_path,
                        "category": item.category,
                        "file_index": index,
                        "files_total": len(items),
                        "file_progress": 100.0,
                        "file_bytes_sent": 0,
                        "file_bytes_total": item.size_bytes,
                        "global_progress": global_progress,
                        "bytes_completed": completed_bytes,
                        "bytes_uploaded": uploaded_bytes,
                        "bytes_total": total_bytes,
                    },
                )
                continue

            error: Exception | None = None
            for file_attempt in range(1, config.retries + 1):
                try:
                    def progress(_event: str, metrics: dict[str, Any]) -> None:
                        if BeamProgressService.is_cancelled():
                            raise RuntimeError("Sincronización Beam cancelada por el usuario.")
                        file_sent = min(item.size_bytes, int(metrics.get("file_bytes_sent") or 0))
                        current_completed = completed_bytes + file_sent
                        elapsed = max(0.001, time.perf_counter() - started)
                        global_speed = int(uploaded_bytes + file_sent) / elapsed
                        remaining = max(0, total_bytes - current_completed)
                        global_eta = int(remaining / global_speed) if global_speed > 0 else None
                        details = {
                            **metrics,
                            "status": "UPLOADING",
                            "file_name": item.source.name,
                            "relative_path": item.relative_path,
                            "remote_path": remote_path,
                            "category": item.category,
                            "file_index": index,
                            "files_total": len(items),
                            "file_attempt": file_attempt,
                            "global_progress": round(100 * current_completed / max(1, total_bytes), 2),
                            "bytes_completed": current_completed,
                            "bytes_uploaded": uploaded_bytes + file_sent,
                            "bytes_total": total_bytes,
                            "global_speed_bps": int(global_speed),
                            "global_eta_seconds": global_eta,
                        }
                        chunk_mb = int(details.get("chunk_size_bytes") or 0) / (1024 * 1024)
                        message = (
                            f"Subiendo {item.relative_path} — archivo {index} de {len(items)}"
                            f" — {float(details.get('file_progress') or 0):.2f}%"
                            f" — {chunk_mb:.0f} MiB/parte"
                        )
                        notify(
                            "beam-uploading",
                            max(1, min(99, int(details["global_progress"]))),
                            message,
                            details,
                        )

                    BeamMultipartClient.upload_file(config, item.source, destination, progress)
                    summary.ok += 1
                    summary.bytes_sent += item.size_bytes
                    completed_bytes += item.size_bytes
                    uploaded_bytes += item.size_bytes
                    error = None
                    break
                except Exception as exc:
                    error = exc
                    if file_attempt < config.retries:
                        time.sleep(min(8, 2 ** file_attempt))

            if error is not None:
                summary.failed += 1
                summary.failures.append({"path": item.relative_path, "error": str(error)})
                notify(
                    "beam-failed",
                    max(1, min(99, int(100 * completed_bytes / max(1, total_bytes)))),
                    f"FAILED {item.relative_path} — archivo {index} de {len(items)}: {error}",
                    {
                        "status": "FAILED",
                        "file_name": item.source.name,
                        "relative_path": item.relative_path,
                        "remote_path": remote_path,
                        "category": item.category,
                        "file_index": index,
                        "files_total": len(items),
                        "attempts": config.retries,
                        "bytes_completed": completed_bytes,
                        "bytes_uploaded": uploaded_bytes,
                        "bytes_total": total_bytes,
                    },
                )

        notify(
            "beam-completed",
            100,
            f"Beam finalizado: {summary.ok} OK, {summary.failed} FAILED, {summary.skipped} SKIPPED.",
            {
                "status": "COMPLETED",
                "files_total": len(items),
                "files_uploaded": summary.ok,
                "files_failed": summary.failed,
                "files_skipped": summary.skipped,
                "global_progress": 100.0,
                "bytes_completed": completed_bytes,
                "bytes_uploaded": uploaded_bytes,
                "bytes_total": total_bytes,
            },
        )
        return {
            "volume_name": config.volume_name,
            "target": BeamVolumeService.remote_uri(config.volume_name, remote_prefix),
            "files_total": len(items),
            "files_uploaded": summary.ok,
            "files_failed": summary.failed,
            "files_skipped": summary.skipped,
            "bytes_total": total_bytes,
            "bytes_completed": completed_bytes,
            "bytes_uploaded": uploaded_bytes,
            "failures": summary.failures,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "transfer_mode": "beam-beta9-direct-multipart",
            "skip_identical": skip_identical,
        }
