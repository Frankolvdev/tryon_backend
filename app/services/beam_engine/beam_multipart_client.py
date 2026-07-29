from __future__ import annotations

import logging
import math
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, Callable

import requests
from requests.adapters import HTTPAdapter

from app.services.beam_engine.beam_config import BeamSyncConfig
from app.services.beam_engine.beam_progress_reader import ProgressReader

ProgressCallback = Callable[[str, dict[str, Any]], None]
CancelCheck = Callable[[], bool]


class BeamUploadCancelled(RuntimeError):
    """Cancelación solicitada por el usuario durante Multipart Beam."""

_MIB = 1024 * 1024
logger = logging.getLogger(__name__)


class BeamMultipartClient:
    """Multipart directo mediante beta9 VolumeService y URLs prefirmadas."""

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
                "El SDK beta9 no está instalado en el mismo entorno Python del backend."
            ) from exc
        return {
            "ServiceClient": ServiceClient,
            "ConfigContext": ConfigContext,
            "CreateMultipartUploadRequest": CreateMultipartUploadRequest,
            "CompleteMultipartUploadRequest": CompleteMultipartUploadRequest,
            "AbortMultipartUploadRequest": AbortMultipartUploadRequest,
            "CompletedPart": CompletedPart,
        }

    @staticmethod
    def _transfer_plan(file_size: int, config: BeamSyncConfig) -> tuple[int, int]:
        """Calcula un tamaño de parte adaptativo antes de subir cada archivo.

        Busca aproximadamente dos partes por worker máximo para que la
        concurrencia adaptativa tenga suficiente trabajo disponible, evitando
        a la vez partes excesivamente pequeñas y demasiadas peticiones HTTP.
        """
        if file_size <= 0:
            return 1, 1

        max_workers = max(1, min(int(config.multipart_workers), 12))
        initial_workers = max(1, min(int(config.adaptive_initial_workers), max_workers))
        target_parts = max(initial_workers * 2, max_workers * 2)

        min_part_size = 32 * _MIB
        max_part_size = 512 * _MIB
        max_parts = 1000
        allowed_part_sizes = (
            32 * _MIB,
            64 * _MIB,
            128 * _MIB,
            256 * _MIB,
            512 * _MIB,
        )

        # Los archivos pequeños no necesitan multipart artificial.
        if file_size <= min_part_size:
            return file_size, 1

        calculated = math.ceil(file_size / target_parts)
        calculated = max(min_part_size, calculated)

        # Redondea hacia arriba al siguiente tamaño permitido.
        chunk_size = next(
            (size for size in allowed_part_sizes if size >= calculated),
            max_part_size,
        )

        # Evita superar MAX_PARTS en archivos excepcionalmente grandes.
        minimum_for_part_limit = math.ceil(file_size / max_parts)
        if minimum_for_part_limit > chunk_size:
            alignment = min_part_size
            chunk_size = math.ceil(minimum_for_part_limit / alignment) * alignment

        chunk_size = min(file_size, chunk_size)
        parts_total = max(1, math.ceil(file_size / chunk_size))
        workers = max(1, min(max_workers, parts_total))
        return chunk_size, workers

    @classmethod
    def upload_file(
        cls,
        config: BeamSyncConfig,
        source: Path,
        destination: str,
        on_progress: ProgressCallback,
        cancel_check: CancelCheck | None = None,
    ) -> dict[str, Any]:
        sdk = cls._sdk()
        cancel_check = cancel_check or (lambda: False)

        def ensure_not_cancelled() -> None:
            if cancel_check():
                raise BeamUploadCancelled("Sincronización Beam cancelada por el usuario.")

        ensure_not_cancelled()
        source = source.resolve()
        if not source.is_file():
            raise FileNotFoundError(str(source))

        remote = destination.replace("\\", "/")
        prefix = f"beam://{config.volume_name}/"
        if not remote.startswith(prefix):
            raise ValueError(f"Destino Beam inválido: {destination}")
        volume_path = remote[len(prefix):].lstrip("/")
        file_size = source.stat().st_size
        chunk_size, workers_requested = cls._transfer_plan(file_size, config)

        context = sdk["ConfigContext"](
            token=config.api_key,
            gateway_host=config.gateway_host,
            gateway_port=config.gateway_port,
        )

        started_at = time.perf_counter()
        state_lock = threading.Lock()
        uploaded_by_part: dict[int, int] = {}
        completed_numbers: set[int] = set()
        active_numbers: set[int] = set()
        attempts_by_part: dict[int, int] = {}
        retry_events = 0
        adaptive_limit = max(1, min(config.adaptive_initial_workers, workers_requested))
        last_attempt_read: dict[int, int] = {}
        last_emit_at = started_at
        last_emit_logical = 0
        last_emit_network = 0
        displayed_bytes = 0
        network_bytes = 0
        smoothed_speed = 0.0
        upload_id = ""
        session_local = threading.local()

        def get_session() -> requests.Session:
            session = getattr(session_local, "session", None)
            if session is None:
                session = requests.Session()
                adapter = HTTPAdapter(
                    pool_connections=workers_requested,
                    pool_maxsize=workers_requested,
                    max_retries=0,
                    pool_block=True,
                )
                session.mount("https://", adapter)
                session.mount("http://", adapter)
                session_local.session = session
            return session

        with sdk["ServiceClient"](context) as client:
            ensure_not_cancelled()
            initial = client.volume.create_multipart_upload(
                sdk["CreateMultipartUploadRequest"](
                    volume_name=config.volume_name,
                    volume_path=volume_path,
                    chunk_size=chunk_size,
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
            workers = max(1, min(workers_requested, parts_total))
            logger.info(
                "[Beam Adaptive] Inicio | archivo=%s | tamaño=%d bytes | partes=%d | "
                "workers_iniciales=%d | workers_máximos=%d | probe=%.1fs",
                source.name,
                file_size,
                parts_total,
                adaptive_limit,
                workers,
                float(config.adaptive_probe_seconds),
            )

            def emit(active_part: int | None, *, force: bool = False) -> None:
                nonlocal last_emit_at, last_emit_logical, last_emit_network
                nonlocal displayed_bytes, smoothed_speed
                now = time.perf_counter()
                with state_lock:
                    raw_logical = min(file_size, sum(uploaded_by_part.values()))
                    # La UI nunca retrocede aunque una parte sea reiniciada por retry.
                    displayed_bytes = max(displayed_bytes, raw_logical)
                    delta_logical = displayed_bytes - last_emit_logical
                    delta_network = network_bytes - last_emit_network
                    delta_time = now - last_emit_at
                    if (
                        not force
                        and delta_time < config.progress_interval_seconds
                        and delta_logical < config.progress_bytes_step
                    ):
                        return
                    instant = max(0, delta_network) / max(0.001, delta_time)
                    smoothed_speed = (
                        instant
                        if smoothed_speed <= 0
                        else smoothed_speed * 0.75 + instant * 0.25
                    )
                    last_emit_at = now
                    last_emit_logical = displayed_bytes
                    last_emit_network = network_bytes
                    remaining = max(0, file_size - displayed_bytes)
                    eta = int(remaining / smoothed_speed) if smoothed_speed > 0 else None
                    active_sorted = sorted(active_numbers)
                    metrics = {
                        "file_progress": round(100.0 * displayed_bytes / max(1, file_size), 2),
                        "file_bytes_sent": displayed_bytes,
                        "file_bytes_total": file_size,
                        "network_bytes_sent": network_bytes,
                        "file_speed_bps": int(smoothed_speed),
                        "file_eta_seconds": eta,
                        # Compatibilidad: part_number ahora es avance confirmado monotónico.
                        "part_number": len(completed_numbers),
                        "parts_completed": len(completed_numbers),
                        "parts_total": parts_total,
                        "parts_active": len(active_sorted),
                        "active_part_numbers": active_sorted,
                        "active_part_number": active_part,
                        "attempt": attempts_by_part.get(active_part or 0, 1),
                        "chunk_size_bytes": chunk_size,
                        "multipart_workers": workers,
                        "adaptive_concurrency": adaptive_limit,
                        "transfer_mode": "beam-beta9-direct-multipart",
                    }
                on_progress("multipart-progress", metrics)

            def upload_part(part: Any) -> Any:
                nonlocal network_bytes, retry_events
                ensure_not_cancelled()
                number = int(part.number)
                start = int(part.start)
                end = int(part.end)
                length = max(0, end - start)
                last_error: Exception | None = None
                for attempt in range(1, config.retries + 1):
                    ensure_not_cancelled()
                    with state_lock:
                        attempts_by_part[number] = attempt
                        uploaded_by_part[number] = 0
                        last_attempt_read[number] = 0
                        active_numbers.add(number)
                    emit(number, force=True)
                    try:
                        with source.open("rb", buffering=config.read_buffer_size_bytes) as handle:
                            handle.seek(start)

                            def part_progress(bytes_in_part: int) -> None:
                                nonlocal network_bytes
                                ensure_not_cancelled()
                                current = min(length, int(bytes_in_part))
                                with state_lock:
                                    previous = last_attempt_read.get(number, 0)
                                    network_bytes += max(0, current - previous)
                                    last_attempt_read[number] = current
                                    uploaded_by_part[number] = current
                                emit(number)

                            reader = ProgressReader(
                                handle,
                                length=length,
                                on_progress=part_progress,
                            )
                            response = get_session().put(
                                str(part.url),
                                data=reader,
                                headers={"Content-Length": str(length)},
                                timeout=(30, config.timeout_seconds),
                            )
                            response.raise_for_status()
                            etag = str(response.headers.get("ETag") or "").strip('"')
                            if not etag:
                                raise RuntimeError(
                                    f"Beam no devolvió ETag para la parte {number}."
                                )
                        with state_lock:
                            uploaded_by_part[number] = length
                            completed_numbers.add(number)
                            active_numbers.discard(number)
                        emit(number, force=True)
                        return sdk["CompletedPart"](number=number, etag=etag)
                    except BeamUploadCancelled:
                        with state_lock:
                            active_numbers.discard(number)
                        raise
                    except Exception as exc:
                        last_error = exc
                        with state_lock:
                            retry_events += 1
                        with state_lock:
                            uploaded_by_part[number] = 0
                            active_numbers.discard(number)
                        emit(number, force=True)
                        if attempt < config.retries:
                            time.sleep(min(8, 2 ** attempt))
                raise RuntimeError(
                    f"Falló la parte {number}/{parts_total} después de "
                    f"{config.retries} intentos: {last_error}"
                )

            try:
                completed_parts = []
                emit(None, force=True)
                pending_parts = iter(parts)
                active_futures: dict[Any, Any] = {}
                last_probe_at = time.perf_counter()
                last_probe_bytes = 0
                last_probe_retries = 0

                def fill_slots(pool: ThreadPoolExecutor) -> None:
                    while len(active_futures) < adaptive_limit:
                        try:
                            next_part = next(pending_parts)
                        except StopIteration:
                            break
                        active_futures[pool.submit(upload_part, next_part)] = next_part

                with ThreadPoolExecutor(
                    max_workers=workers,
                    thread_name_prefix="beam-multipart",
                ) as pool:
                    fill_slots(pool)
                    while active_futures:
                        ensure_not_cancelled()
                        done, _ = wait(
                            tuple(active_futures),
                            timeout=0.5,
                            return_when=FIRST_COMPLETED,
                        )
                        if not done:
                            emit(None)
                            continue
                        for future in done:
                            active_futures.pop(future, None)
                            completed_parts.append(future.result())

                        now = time.perf_counter()
                        probe_elapsed = now - last_probe_at
                        if probe_elapsed >= config.adaptive_probe_seconds:
                            with state_lock:
                                probe_bytes = network_bytes
                                probe_retries = retry_events
                            delta_bytes = max(0, probe_bytes - last_probe_bytes)
                            delta_retries = max(0, probe_retries - last_probe_retries)
                            probe_speed = delta_bytes / max(0.001, probe_elapsed)

                            previous_limit = adaptive_limit
                            decision = "mantener"
                            reason = "sin cambio útil"
                            if delta_retries > 0 and adaptive_limit > 1:
                                adaptive_limit = max(1, adaptive_limit - 1)
                                decision = "reducir"
                                reason = f"{delta_retries} reintento(s) detectado(s)"
                            elif probe_speed > 0 and adaptive_limit < workers:
                                adaptive_limit = min(
                                    workers,
                                    adaptive_limit + max(1, config.adaptive_step_workers),
                                )
                                decision = "aumentar"
                                reason = "transferencia activa sin reintentos"
                            elif adaptive_limit >= workers:
                                reason = "límite máximo alcanzado"
                            elif probe_speed <= 0:
                                reason = "sin transferencia medible"

                            logger.info(
                                "[Beam Adaptive] Probe | archivo=%s | intervalo=%.2fs | "
                                "velocidad=%.2f MiB/s | reintentos=%d | workers=%d->%d | "
                                "decisión=%s | motivo=%s | activas=%d | completadas=%d/%d",
                                source.name,
                                probe_elapsed,
                                probe_speed / _MIB,
                                delta_retries,
                                previous_limit,
                                adaptive_limit,
                                decision,
                                reason,
                                len(active_futures),
                                len(completed_parts),
                                parts_total,
                            )

                            last_probe_at = now
                            last_probe_bytes = probe_bytes
                            last_probe_retries = probe_retries
                            emit(None, force=True)

                        fill_slots(pool)
                completed_parts.sort(key=lambda part: int(part.number))
                ensure_not_cancelled()
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
                    displayed_bytes = file_size
                    completed_numbers.update(int(part.number) for part in parts)
                    active_numbers.clear()
                emit(None, force=True)
                elapsed_total = max(0.001, time.perf_counter() - started_at)
                logger.info(
                    "[Beam Adaptive] Final | archivo=%s | workers_finales=%d | "
                    "velocidad_media=%.2f MiB/s | tiempo=%.2fs | reintentos=%d",
                    source.name,
                    adaptive_limit,
                    (network_bytes / elapsed_total) / _MIB,
                    elapsed_total,
                    retry_events,
                )
                return {
                    "upload_id": upload_id,
                    "parts_total": parts_total,
                    "parts_completed": parts_total,
                    "bytes_sent": file_size,
                    "network_bytes_sent": network_bytes,
                    "chunk_size_bytes": chunk_size,
                    "multipart_workers": workers,
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
