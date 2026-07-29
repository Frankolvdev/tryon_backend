from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.services.beam_v4.engine import BeamV4Engine

Notify = Callable[[str, int, str], None]


def _human(value: int) -> str:
    amount = float(max(0, value))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or unit == "TB":
            return f"{int(amount)} B" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TB"


class BeamV4ExportAdapter:
    """Adaptador exclusivo entre el exportador existente y Beam V4."""

    @classmethod
    def export(
        cls,
        session: Session,
        *,
        models_root: Path,
        remote_path: str,
        overwrite: bool,
        notify: Notify,
        logical_models: list[dict[str, Any]],
    ) -> dict[str, Any]:
        files = sorted(path for path in models_root.rglob("*") if path.is_file())
        physical_total = len(files)
        bytes_total = sum(path.stat().st_size for path in files)
        logical_total = len({
            str(item.get("target_path") or "").replace("\\", "/").strip("/")
            for item in logical_models if item.get("found", True) and item.get("target_path")
        })
        latest_percent = 94
        started = time.perf_counter()

        def progress(event: dict[str, Any]) -> None:
            nonlocal latest_percent
            phase = str(event.get("phase") or "transfer-progress")
            transferred = int(event.get("bytes_transferred") or event.get("bytes_uploaded") or 0)
            pending_bytes = max(1, int(event.get("bytes_pending") or bytes_total or 1))
            latest_percent = max(latest_percent, min(99, 94 + int(5 * min(1.0, transferred / pending_bytes))))
            name = str(event.get("file_name") or "")
            native = str(event.get("native_line") or "").strip()
            if phase == "inventory":
                message = f"Beam V4 aislado: inventario de {physical_total} archivos ({_human(bytes_total)}). CLI: {event.get('cli_version', '')}"
            elif phase == "file-skipped":
                message = f"Beam V4: OMITIDO {event.get('files_skipped', 0)}/{physical_total} · {name} · {_human(int(event.get('file_size') or 0))}"
            elif phase == "file-queued":
                message = f"Beam V4: PREPARADO {event.get('queue_index', 0)}/{event.get('queued_total', 0)} · {name} · {_human(int(event.get('file_size') or 0))}"
            elif phase == "transfer-start":
                message = f"Beam V4: multipart forzado, una sola transferencia · {event.get('files_pending', 0)} archivos · {_human(int(event.get('bytes_pending') or 0))} · {event.get('destination', '')}"
            elif phase == "transfer-progress":
                message = f"Beam V4: SUBIENDO {_human(transferred)} de {_human(pending_bytes)}"
                speed = int(event.get("speed_bps") or 0)
                if speed:
                    message += f" · {_human(speed)}/s"
                if event.get("eta"):
                    message += f" · ETA {event['eta']}"
                if native:
                    message += f" · CLI: {native[-350:]}"
            elif phase == "file-completed":
                message = f"Beam V4: CONFIRMADO {event.get('completed_index', 0)}/{event.get('files_uploaded', 0)} · {name}"
            elif phase == "completed":
                elapsed = max(0.001, time.perf_counter() - started)
                uploaded = int(event.get("bytes_uploaded") or 0)
                message = f"Beam V4 completado: {event.get('files_uploaded', 0)} subidos, {event.get('files_skipped', 0)} omitidos, {_human(uploaded)} · media {_human(int(uploaded / elapsed))}/s"
            else:
                message = f"Beam V4: {phase}"
            notify(f"beam-v4-{phase}", latest_percent, message)

        result = BeamV4Engine.upload(
            session,
            models_root=models_root,
            remote_prefix=remote_path,
            overwrite=overwrite,
            timeout=86400,
            on_progress=progress,
        )
        return {
            "volume_name": result["volume_name"],
            "path": result.get("path", ""),
            "target": f"beam://{result['volume_name']}" + (f"/{result['path']}" if result.get("path") else ""),
            "overwrite_requested": overwrite,
            "models_uploaded": logical_total,
            "files_total": int(result.get("files_total") or physical_total),
            "files_uploaded": int(result.get("files_uploaded") or 0),
            "files_skipped": int(result.get("files_skipped") or 0),
            "bytes_total": int(result.get("bytes_total") or bytes_total),
            "bytes_uploaded": int(result.get("bytes_uploaded") or 0),
            "bytes_skipped": int(result.get("bytes_skipped") or 0),
            "transfer_mode": "beam-v4-isolated-directory-multipart-forced",
            "transfer_modes": result.get("transfer_modes") or [],
            "parallel_workers": int(result.get("workers") or 0),
            "beam_cli_version": str(result.get("cli_version") or ""),
        }
