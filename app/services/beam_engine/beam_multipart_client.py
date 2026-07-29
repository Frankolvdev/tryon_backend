from __future__ import annotations

import posixpath
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import requests

from app.services.beam_engine.beam_config import BeamSyncConfig
from app.services.beam_engine.beam_progress_reader import ProgressReader

LineCallback = Callable[[str, dict[str, Any]], None]


@dataclass(frozen=True)
class _RemoteTarget:
    volume_name: str
    volume_path: str


class BeamMultipartClient:
    """Independent Beam multipart uploader using beta9 RPC + presigned PUTs."""

    @staticmethod
    def _remote_target(destination: str) -> _RemoteTarget:
        normalized = str(destination or "").replace("\\", "/").strip()
        if not normalized.startswith("beam://"):
            raise ValueError("El destino Beam debe comenzar con beam://")
        payload = normalized[len("beam://") :].lstrip("/")
        volume_name, separator, raw_path = payload.partition("/")
        volume_name = volume_name.strip()
        if not volume_name:
            raise ValueError("El destino Beam no contiene nombre de volumen.")
        clean_parts = [part for part in raw_path.split("/") if part not in {"", ".", ".."}]
        volume_path = posixpath.join(*clean_parts) if clean_parts else ""
        if not separator or not volume_path:
            raise ValueError("El destino Beam debe incluir la ruta remota del archivo.")
        return _RemoteTarget(volume_name=volume_name, volume_path=volume_path)

    @staticmethod
    def _sdk(config: BeamSyncConfig):
        try:
            import beam  # noqa: F401 - activates Beam-specific beta9 defaults
            from beta9.channel import get_channel
            from beta9.clients.volume import (
                AbortMultipartUploadRequest,
                CompletedPart,
                CompleteMultipartUploadRequest,
                CreateMultipartUploadRequest,
                VolumeServiceStub,
            )
            from beta9.config import ConfigContext
        except Exception as exc:  # pragma: no cover - depends on installed SDK
            raise RuntimeError(
                "El SDK beta9 de Beam no está disponible en el venv del backend. "
                'Ejecuta: pip install --upgrade "beam-client>=0.2.202,<0.3".'
            ) from exc

        token = str(config.env.get("BEAM_TOKEN") or "").strip()
        if not token:
            raise RuntimeError("No se encontró BEAM_TOKEN para autenticar el SDK de Beam.")
        host = str(config.env.get("GATEWAY_HOST") or "gateway.beam.cloud").strip()
        port = int(config.env.get("GATEWAY_PORT") or 443)
        context = ConfigContext(token=token, gateway_host=host, gateway_port=port)
        channel = get_channel(context)
        service = VolumeServiceStub(channel)
        return {
            "channel": channel,
            "service": service,
            "create_request": CreateMultipartUploadRequest,
            "complete_request": CompleteMultipartUploadRequest,
            "abort_request": AbortMultipartUploadRequest,
            "completed_part": CompletedPart,
        }

    @staticmethod
    def _response_error(response: Any, fallback: str) -> str:
        return str(
            getattr(response, "err_msg", "")
            or getattr(response, "error_msg", "")
            or fallback
        )

    @classmethod
    def upload_file(
        cls,
        config: BeamSyncConfig,
        source: Path,
        destination: str,
        on_line: LineCallback,
    ) -> None:
        source = Path(source).resolve()
        if not source.is_file():
            raise FileNotFoundError(f"No existe el archivo a subir: {source}")
        file_size = source.stat().st_size
        target = cls._remote_target(destination)
        sdk = cls._sdk(config)
        channel = sdk["channel"]
        service = sdk["service"]
        upload_id = ""
        started_at = time.perf_counter()

        try:
            created = service.create_multipart_upload(
                sdk["create_request"](
                    volume_name=target.volume_name,
                    volume_path=target.volume_path,
                    chunk_size=config.multipart_part_size_bytes,
                    file_size=file_size,
                )
            )
            if not getattr(created, "ok", False):
                raise RuntimeError(cls._response_error(created, "Beam no pudo iniciar Multipart."))
            upload_id = str(getattr(created, "upload_id", "") or "")
            parts = list(getattr(created, "file_upload_parts", None) or [])
            if not upload_id:
                raise RuntimeError("Beam inició Multipart sin devolver upload_id.")
            if file_size > 0 and not parts:
                raise RuntimeError("Beam inició Multipart sin devolver URLs de partes.")

            state_lock = threading.Lock()
            emit_lock = threading.Lock()
            uploaded_by_part: dict[int, int] = {
                int(getattr(part, "number")): 0 for part in parts
            }
            last_emit_at = started_at
            last_emit_bytes = 0
            last_sample_at = started_at
            last_sample_bytes = 0
            smoothed_speed = 0.0

            def report(part_number: int, bytes_in_part: int, attempt: int, *, force: bool = False) -> None:
                nonlocal last_emit_at, last_emit_bytes, last_sample_at, last_sample_bytes, smoothed_speed
                now = time.perf_counter()
                with state_lock:
                    uploaded_by_part[part_number] = max(0, int(bytes_in_part))
                    total_sent = min(file_size, sum(uploaded_by_part.values()))
                with emit_lock:
                    delta_time = max(0.001, now - last_sample_at)
                    delta_bytes = max(0, total_sent - last_sample_bytes)
                    if delta_bytes > 0:
                        instant_speed = delta_bytes / delta_time
                        smoothed_speed = (
                            instant_speed if smoothed_speed <= 0 else smoothed_speed * 0.75 + instant_speed * 0.25
                        )
                        last_sample_at = now
                        last_sample_bytes = total_sent
                    should_emit = (
                        force
                        or now - last_emit_at >= config.progress_interval_seconds
                        or total_sent - last_emit_bytes >= config.progress_bytes_step
                        or total_sent >= file_size
                    )
                    if not should_emit:
                        return
                    speed = int(max(0.0, smoothed_speed))
                    remaining = max(0, file_size - total_sent)
                    eta = int(remaining / speed) if speed else 0
                    metrics = {
                        "native_line": "Beam Multipart directo",
                        "file_progress": round(100.0 * total_sent / max(1, file_size), 2),
                        "file_bytes_sent": total_sent,
                        "file_bytes_total": file_size,
                        "file_speed_bps": speed,
                        "file_eta_seconds": eta,
                        # Compatibility with the existing progress consumer.
                        "speed_bps": speed,
                        "eta_seconds": eta,
                        "part_number": part_number,
                        "parts_total": len(parts),
                        "attempt": attempt,
                    }
                    on_line(
                        f"Multipart parte {part_number}/{len(parts)} · {metrics['file_progress']:.2f}%",
                        metrics,
                    )
                    last_emit_at = now
                    last_emit_bytes = total_sent

            def reset_part(part_number: int, attempt: int) -> None:
                with state_lock:
                    uploaded_by_part[part_number] = 0
                report(part_number, 0, attempt, force=True)

            def upload_part(part: Any) -> Any:
                part_number = int(getattr(part, "number"))
                start = int(getattr(part, "start"))
                end = int(getattr(part, "end"))
                signed_url = str(getattr(part, "url") or "")
                length = end - start
                if length < 0 or not signed_url:
                    raise RuntimeError(f"Beam devolvió una parte inválida: {part_number}")
                last_error: Exception | None = None
                for attempt in range(1, config.retries + 1):
                    reset_part(part_number, attempt)
                    try:
                        with source.open("rb") as file:
                            file.seek(start)
                            reader = ProgressReader(
                                file,
                                length=length,
                                on_progress=lambda consumed, pn=part_number, a=attempt: report(pn, consumed, a),
                            )
                            response = requests.put(
                                signed_url,
                                data=reader,
                                headers={"Content-Length": str(length)},
                                timeout=(30, config.timeout_seconds),
                            )
                            response.raise_for_status()
                            etag = str(response.headers.get("ETag") or response.headers.get("etag") or "").strip('"')
                            if not etag:
                                raise RuntimeError(f"La parte {part_number} terminó sin ETag.")
                        report(part_number, length, attempt, force=True)
                        return sdk["completed_part"](number=part_number, etag=etag)
                    except Exception as exc:
                        last_error = exc
                        reset_part(part_number, attempt)
                        if "cancelada por el usuario" in str(exc).casefold():
                            raise
                        if attempt >= config.retries:
                            break
                        time.sleep(min(8, 2**attempt))
                raise RuntimeError(
                    f"Falló la parte {part_number} después de {config.retries} intentos: {last_error}"
                ) from last_error

            completed_parts: list[Any] = []
            futures: list[Future[Any]] = []
            with ThreadPoolExecutor(max_workers=config.multipart_workers, thread_name_prefix="beam-multipart") as executor:
                futures = [executor.submit(upload_part, part) for part in parts]
                try:
                    for future in as_completed(futures, timeout=config.timeout_seconds):
                        completed_parts.append(future.result())
                except BaseException:
                    for future in futures:
                        future.cancel()
                    raise

            completed_parts.sort(key=lambda item: int(getattr(item, "number")))
            completed = service.complete_multipart_upload(
                sdk["complete_request"](
                    upload_id=upload_id,
                    volume_name=target.volume_name,
                    volume_path=target.volume_path,
                    completed_parts=completed_parts,
                )
            )
            if not getattr(completed, "ok", False):
                raise RuntimeError(cls._response_error(completed, "Beam no pudo completar Multipart."))
            on_line(
                "Transferencia multipart directa completada.",
                {
                    "native_line": "Transferencia multipart directa completada.",
                    "file_progress": 100.0,
                    "file_bytes_sent": file_size,
                    "file_bytes_total": file_size,
                    "file_speed_bps": int(file_size / max(0.001, time.perf_counter() - started_at)),
                    "file_eta_seconds": 0,
                    "speed_bps": int(file_size / max(0.001, time.perf_counter() - started_at)),
                    "eta_seconds": 0,
                    "part_number": len(parts),
                    "parts_total": len(parts),
                    "attempt": 1,
                },
            )
        except BaseException:
            if upload_id:
                try:
                    service.abort_multipart_upload(
                        sdk["abort_request"](
                            upload_id=upload_id,
                            volume_name=target.volume_name,
                            volume_path=target.volume_path,
                        )
                    )
                except Exception:
                    pass
            raise
        finally:
            try:
                channel.close()
            except Exception:
                pass
