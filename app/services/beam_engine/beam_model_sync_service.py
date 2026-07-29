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
            relative = str(
                raw.get("target_path") or raw.get("relative_path") or source.name
            ).replace("\\", "/")
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
        try:
            items = cls._items(manifest_models)
            summary = BeamSyncSummary()
            total_bytes = sum(item.size_bytes for item in items)
            completed_bytes = 0
            uploaded_bytes = 0
            inventory = BeamVolumeService.metadata_index(config) if skip_identical else {}
            started = time.perf_counter()

            for index, item in enumerate(items, 1):
                if BeamProgressService.is_cancelled():
                    raise RuntimeError("Sincronización Beam cancelada por el usuario.")
                remote_path = "/".join(
                    part
                    for part in (
                        remote_prefix.strip("/\\").replace("\\", "/"),
                        item.relative_path,
                    )
                    if part
                )
                destination = BeamVolumeService.remote_uri(config.volume_name, remote_path)

                if skip_identical and remote_path in inventory:
                    summary.skipped += 1
                    completed_bytes += item.size_bytes
                    elapsed = max(0.001, time.perf_counter() - started)
                    global_speed = int(uploaded_bytes / elapsed)
                    remaining = max(0, total_bytes - completed_bytes)
                    notify(
                        "beam-skipped",
                        max(1, min(100, int(100 * completed_bytes / max(1, total_bytes)))),
                        f"SKIPPED {item.relative_path}",
                        {
                            "file_name": item.source.name,
                            "relative_path": item.relative_path,
                            "category": item.category,
                            "file_index": index,
                            "files_total": len(items),
                            "file_progress": 100.0,
                            "file_bytes_sent": 0,
                            "file_bytes_total": item.size_bytes,
                            "file_speed_bps": 0,
                            "file_eta_seconds": 0,
                            "global_progress": round(100 * completed_bytes / max(1, total_bytes), 2),
                            "bytes_completed": completed_bytes,
                            "bytes_uploaded": uploaded_bytes,
                            "bytes_total": total_bytes,
                            "global_speed_bps": global_speed,
                            "global_eta_seconds": int(remaining / global_speed) if global_speed else 0,
                            # Compatibility aliases.
                            "bytes_sent": uploaded_bytes,
                            "speed_bps": 0,
                            "eta_seconds": 0,
                            "status": "SKIPPED",
                        },
                    )
                    continue

                error: Exception | None = None
                try:
                    def line(_text: str, metrics: dict[str, Any]) -> None:
                        if BeamProgressService.is_cancelled():
                            raise RuntimeError("Sincronización Beam cancelada por el usuario.")
                        file_sent = min(item.size_bytes, int(metrics.get("file_bytes_sent") or 0))
                        current_completed = min(total_bytes, completed_bytes + file_sent)
                        elapsed = max(0.001, time.perf_counter() - started)
                        file_speed = int(metrics.get("file_speed_bps") or metrics.get("speed_bps") or 0)
                        global_speed = int((uploaded_bytes + file_sent) / elapsed)
                        global_remaining = max(0, total_bytes - current_completed)
                        details = {
                            **metrics,
                            "file_name": item.source.name,
                            "category": item.category,
                            "relative_path": item.relative_path,
                            "file_index": index,
                            "files_total": len(items),
                            "file_progress": round(100 * file_sent / max(1, item.size_bytes), 2),
                            "file_bytes_sent": file_sent,
                            "file_bytes_total": item.size_bytes,
                            "file_speed_bps": file_speed,
                            "file_eta_seconds": int((item.size_bytes - file_sent) / file_speed) if file_speed else 0,
                            "global_progress": round(100 * current_completed / max(1, total_bytes), 2),
                            "bytes_completed": current_completed,
                            "bytes_uploaded": uploaded_bytes + file_sent,
                            "bytes_total": total_bytes,
                            "global_speed_bps": global_speed,
                            "global_eta_seconds": int(global_remaining / global_speed) if global_speed else 0,
                            # Compatibility aliases consumed by the current panel.
                            "bytes_sent": uploaded_bytes + file_sent,
                            "speed_bps": file_speed,
                            "eta_seconds": int((item.size_bytes - file_sent) / file_speed) if file_speed else 0,
                            "status": "UPLOADING",
                        }
                        notify(
                            "beam-uploading",
                            max(1, min(99, int(details["global_progress"]))),
                            f"Beam {item.source.name} · {index}/{len(items)} · {details['file_progress']:.1f}%",
                            details,
                        )

                    BeamMultipartClient.upload_file(config, item.source, destination, line)
                    summary.ok += 1
                    summary.bytes_sent += item.size_bytes
                    uploaded_bytes += item.size_bytes
                    completed_bytes += item.size_bytes
                except Exception as exc:
                    error = exc

                if error is not None:
                    summary.failed += 1
                    summary.failures.append({"path": item.relative_path, "error": str(error)})
                    # A failed file is complete from the job traversal perspective,
                    # so the global bar can continue to the next file without
                    # pretending that its bytes were uploaded.
                    completed_bytes += item.size_bytes
                    notify(
                        "beam-failed",
                        max(1, min(100, int(100 * completed_bytes / max(1, total_bytes)))),
                        f"FAILED {item.relative_path}: {error}",
                        {
                            "file_name": item.source.name,
                            "category": item.category,
                            "relative_path": item.relative_path,
                            "file_index": index,
                            "files_total": len(items),
                            "global_progress": round(100 * completed_bytes / max(1, total_bytes), 2),
                            "bytes_completed": completed_bytes,
                            "bytes_uploaded": uploaded_bytes,
                            "bytes_total": total_bytes,
                            "status": "FAILED",
                            "attempts": config.retries,
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
                "multipart_part_size_mb": config.multipart_part_size_mb,
                "multipart_workers": config.multipart_workers,
            }
        finally:
            config.cleanup()
