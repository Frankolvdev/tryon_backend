from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

import requests

from app.services.beam_engine.beam_config import BeamSyncConfig
from app.services.beam_engine.beam_progress_reader import ProgressReader

ProgressCallback = Callable[[str, dict[str, Any]], None]


class BeamMultipartClient:
    """Cliente Multipart directo del SDK beta9/Beam; no ejecuta Beam CLI."""

    @staticmethod
    def _sdk():
        try:
            from beta9.channel import ServiceClient
            from beta9.clients.volume import (
                AbortMultipartUploadRequest,
                CompletedPart,
                CompleteMultipartUploadRequest,
                CreateMultipartUploadRequest,
            )
            from beta9.config import ConfigContext
        except ImportError as exc:
            raise RuntimeError(
                "El SDK beta9 no está instalado en el mismo entorno Python del backend. "
                "Instala el paquete Beam/beta9 en este entorno; no se usará Beam CLI."
            ) from exc
        return {
            "ServiceClient": ServiceClient,
            "ConfigContext": ConfigContext,
            "CreateMultipartUploadRequest": CreateMultipartUploadRequest,
            "CompleteMultipartUploadRequest": CompleteMultipartUploadRequest,
            "AbortMultipartUploadRequest": AbortMultipartUploadRequest,
            "CompletedPart": CompletedPart,
        }

    @classmethod
    def upload_file(
        cls,
        config: BeamSyncConfig,
        source: Path,
        destination: str,
        on_progress: ProgressCallback,
    ) -> dict[str, Any]:
        sdk = cls._sdk()
        source = source.resolve()
        if not source.is_file():
            raise FileNotFoundError(str(source))

        remote = destination.replace("\\", "/")
        prefix = f"beam://{config.volume_name}/"
        if not remote.startswith(prefix):
            raise ValueError(f"Destino Beam inválido: {destination}")
        volume_path = remote[len(prefix):].lstrip("/")
        file_size = source.stat().st_size
        requested_chunk = max(5, config.multipart_part_size_mb) * 1024 * 1024

        context = sdk["ConfigContext"](
            token=config.api_key,
            gateway_host=config.gateway_host,
            gateway_port=config.gateway_port,
        )

        started_at = time.perf_counter()
        state_lock = threading.Lock()
        uploaded_by_part: dict[int, int] = {}
        last_emit_at = started_at
        last_emit_bytes = 0
        smoothed_speed = 0.0
        upload_id = ""

        with sdk["ServiceClient"](context) as client:
            initial = client.volume.create_multipart_upload(
                sdk["CreateMultipartUploadRequest"](
                    volume_name=config.volume_name,
                    volume_path=volume_path,
                    chunk_size=requested_chunk,
                    file_size=file_size,
                )
            )
            if not getattr(initial, "ok", False):
                raise RuntimeError(
                    "Beam no pudo iniciar Multipart: "
                    + str(getattr(initial, "err_msg", "respuesta inválida"))
                )
            upload_id = str(initial.upload_id)
            parts = list(initial.file_upload_parts)
            parts_total = len(parts)
            if not parts:
                raise RuntimeError("Beam inició Multipart sin devolver partes prefirmadas.")

            def emit(part_number: int, attempt: int, *, force: bool = False) -> None:
                nonlocal last_emit_at, last_emit_bytes, smoothed_speed
                now = time.perf_counter()
                with state_lock:
                    total_sent = min(file_size, sum(uploaded_by_part.values()))
                    delta_bytes = total_sent - last_emit_bytes
                    delta_time = now - last_emit_at
                    if not force and delta_time < config.progress_interval_seconds and delta_bytes < config.progress_bytes_step:
                        return
                    instant = delta_bytes / max(0.001, delta_time) if delta_bytes >= 0 else 0.0
                    smoothed_speed = instant if smoothed_speed <= 0 else smoothed_speed * 0.75 + instant * 0.25
                    last_emit_at = now
                    last_emit_bytes = total_sent
                    elapsed = max(0.001, now - started_at)
                    average_speed = total_sent / elapsed
                    speed = int(smoothed_speed or average_speed)
                    remaining = max(0, file_size - total_sent)
                    eta = int(remaining / speed) if speed > 0 else None
                    metrics = {
                        "file_progress": round(100.0 * total_sent / max(1, file_size), 2),
                        "file_bytes_sent": total_sent,
                        "file_bytes_total": file_size,
                        "file_speed_bps": speed,
                        "file_eta_seconds": eta,
                        "part_number": part_number,
                        "parts_total": parts_total,
                        "attempt": attempt,
                        "transfer_mode": "beam-beta9-direct-multipart",
                    }
                on_progress("multipart-progress", metrics)

            def upload_part(part: Any) -> Any:
                number = int(part.number)
                start = int(part.start)
                end = int(part.end)
                length = max(0, end - start)
                last_error: Exception | None = None
                for attempt in range(1, config.retries + 1):
                    with state_lock:
                        uploaded_by_part[number] = 0
                    emit(number, attempt, force=True)
                    try:
                        with source.open("rb") as handle:
                            handle.seek(start)

                            def part_progress(bytes_in_part: int) -> None:
                                with state_lock:
                                    uploaded_by_part[number] = min(length, int(bytes_in_part))
                                emit(number, attempt)

                            reader = ProgressReader(handle, length=length, on_progress=part_progress)
                            response = requests.put(
                                str(part.url),
                                data=reader,
                                headers={"Content-Length": str(length)},
                                timeout=(30, config.timeout_seconds),
                            )
                            response.raise_for_status()
                            etag = str(response.headers.get("ETag") or "").strip('"')
                            if not etag:
                                raise RuntimeError(f"Beam no devolvió ETag para la parte {number}.")
                        with state_lock:
                            uploaded_by_part[number] = length
                        emit(number, attempt, force=True)
                        return sdk["CompletedPart"](number=number, etag=etag)
                    except Exception as exc:
                        last_error = exc
                        with state_lock:
                            uploaded_by_part[number] = 0
                        emit(number, attempt, force=True)
                        if attempt < config.retries:
                            time.sleep(min(8, 2 ** attempt))
                raise RuntimeError(
                    f"Falló la parte {number}/{parts_total} después de {config.retries} intentos: {last_error}"
                )

            try:
                completed_parts = []
                workers = max(1, min(config.multipart_workers, parts_total))
                with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="beam-multipart") as pool:
                    futures = [pool.submit(upload_part, part) for part in parts]
                    for future in as_completed(futures):
                        completed_parts.append(future.result())
                completed_parts.sort(key=lambda part: int(part.number))
                completed = client.volume.complete_multipart_upload(
                    sdk["CompleteMultipartUploadRequest"](
                        upload_id=upload_id,
                        volume_name=config.volume_name,
                        volume_path=volume_path,
                        completed_parts=completed_parts,
                    )
                )
                if not getattr(completed, "ok", False):
                    raise RuntimeError(
                        "Beam no pudo completar Multipart: "
                        + str(getattr(completed, "err_msg", "respuesta inválida"))
                    )
                with state_lock:
                    for part in parts:
                        uploaded_by_part[int(part.number)] = max(0, int(part.end) - int(part.start))
                emit(parts_total, 1, force=True)
                return {
                    "upload_id": upload_id,
                    "parts_total": parts_total,
                    "bytes_sent": file_size,
                    "transfer_mode": "beam-beta9-direct-multipart",
                }
            except BaseException:
                try:
                    client.volume.abort_multipart_upload(
                        sdk["AbortMultipartUploadRequest"](
                            upload_id=upload_id,
                            volume_name=config.volume_name,
                            volume_path=volume_path,
                        )
                    )
                finally:
                    raise
