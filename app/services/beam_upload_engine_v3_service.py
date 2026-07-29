from __future__ import annotations

import os
import queue
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.services.beam_file_manager_service import BeamFileManagerError, BeamFileManagerService

ProgressCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class BeamUploadItem:
    local_path: Path
    remote_path: str
    size: int


class BeamUploadEngineV3Service:
    """Motor de subida Beam V3, aislado del File Manager y otros proveedores.

    Prioriza ``beam cp`` directo al destino final y consume la salida de la CLI
    en vivo. Si la versión instalada no acepta destinos anidados en Windows,
    retrocede únicamente para ese archivo al transporte seguro raíz + ``mv``.
    """

    ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
    BYTE_RE = re.compile(
        r"(?P<done>[0-9]+(?:[.,][0-9]+)?)\s*(?P<done_unit>KiB|MiB|GiB|TiB|KB|MB|GB|TB|B)"
        r"\s*(?:/|of)\s*"
        r"(?P<total>[0-9]+(?:[.,][0-9]+)?)\s*(?P<total_unit>KiB|MiB|GiB|TiB|KB|MB|GB|TB|B)",
        re.IGNORECASE,
    )
    SPEED_RE = re.compile(
        r"(?P<speed>[0-9]+(?:[.,][0-9]+)?)\s*(?P<unit>KiB|MiB|GiB|TiB|KB|MB|GB|TB|B)\s*/\s*s",
        re.IGNORECASE,
    )
    PERCENT_RE = re.compile(r"(?P<percent>[0-9]{1,3}(?:[.,][0-9]+)?)\s*%")
    UNIT = {
        "B": 1,
        "KB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "TB": 1000**4,
        "KIB": 1024,
        "MIB": 1024**2,
        "GIB": 1024**3,
        "TIB": 1024**4,
    }
    DIRECT_DESTINATION_FAILURES = (
        "invalid volume name",
        "volume not found",
        "failed to parse",
        "invalid destination",
        "invalid path",
        "cannot find volume",
    )

    @classmethod
    def _number(cls, value: str, unit: str) -> int:
        return int(float(value.replace(",", ".")) * cls.UNIT[unit.upper()])

    @classmethod
    def _parse_native_progress(cls, text: str, expected_size: int) -> dict[str, Any]:
        clean = cls.ANSI_RE.sub("", text or "").strip()
        result: dict[str, Any] = {"native_line": clean}
        byte_match = cls.BYTE_RE.search(clean)
        if byte_match:
            result["file_bytes_transferred"] = cls._number(
                byte_match.group("done"), byte_match.group("done_unit")
            )
            result["file_bytes_total"] = cls._number(
                byte_match.group("total"), byte_match.group("total_unit")
            )
        else:
            percent_match = cls.PERCENT_RE.search(clean)
            if percent_match and expected_size > 0:
                percent = min(100.0, max(0.0, float(percent_match.group("percent").replace(",", "."))))
                result["file_bytes_transferred"] = int(expected_size * percent / 100.0)
                result["file_bytes_total"] = expected_size
        speed_match = cls.SPEED_RE.search(clean)
        if speed_match:
            result["speed_bps"] = cls._number(speed_match.group("speed"), speed_match.group("unit"))
        return result

    @staticmethod
    def _reader(stream: Any, output_queue: queue.Queue[tuple[str, str]], source: str) -> None:
        try:
            buffer = ""
            while True:
                chunk = stream.read(1)
                if chunk == "":
                    if buffer:
                        output_queue.put((source, buffer))
                    break
                if chunk in {"\r", "\n"}:
                    if buffer.strip():
                        output_queue.put((source, buffer))
                    buffer = ""
                else:
                    buffer += chunk
        finally:
            try:
                stream.close()
            except Exception:
                pass

    @classmethod
    def _stream_command(
        cls,
        *,
        executable: str,
        env: dict[str, str],
        args: list[str],
        timeout: int,
        item: BeamUploadItem,
        emit: ProgressCallback,
        base_event: dict[str, Any],
    ) -> str:
        process = subprocess.Popen(
            [executable, *args],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            bufsize=0,
        )
        output_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        threads = [
            threading.Thread(target=cls._reader, args=(process.stdout, output_queue, "stdout"), daemon=True),
            threading.Thread(target=cls._reader, args=(process.stderr, output_queue, "stderr"), daemon=True),
        ]
        for thread in threads:
            thread.start()

        started = time.monotonic()
        lines: list[str] = []
        last_emit = 0.0
        latest_bytes = 0
        while process.poll() is None or any(thread.is_alive() for thread in threads) or not output_queue.empty():
            if time.monotonic() - started > max(10, int(timeout)):
                process.kill()
                raise BeamFileManagerError(
                    f"Beam CLI excedió {timeout} segundos subiendo {item.local_path.name}."
                )
            try:
                source, line = output_queue.get(timeout=0.15)
            except queue.Empty:
                continue
            clean = cls.ANSI_RE.sub("", line).strip()
            if not clean:
                continue
            lines.append(f"[{source}] {clean}")
            parsed = cls._parse_native_progress(clean, item.size)
            current_bytes = int(parsed.get("file_bytes_transferred") or 0)
            if current_bytes:
                latest_bytes = max(latest_bytes, min(item.size, current_bytes))
            now = time.monotonic()
            # Evita inundar el historial, pero conserva cada cambio útil de la CLI.
            if now - last_emit >= 0.35 or current_bytes >= item.size:
                event = dict(base_event)
                event.update(parsed)
                event["file_bytes_transferred"] = latest_bytes
                event["phase"] = "file-progress"
                emit(event)
                last_emit = now

        return_code = process.wait()
        output = "\n".join(lines)
        if return_code != 0:
            raise BeamFileManagerError((output or "Beam CLI terminó con error")[-8000:])
        return output

    @classmethod
    def _is_nested_destination_failure(cls, exc: Exception) -> bool:
        lowered = str(exc).casefold()
        return any(marker in lowered for marker in cls.DIRECT_DESTINATION_FAILURES)

    @classmethod
    def upload_tree(
        cls,
        db: Session,
        *,
        volume: str,
        models_root: Path,
        remote_prefix: str,
        overwrite: bool,
        timeout: int,
        workers: int = 3,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        emit = on_progress or (lambda _event: None)
        cfg, executable, env, home = BeamFileManagerService._env(db)
        selected = BeamFileManagerService._volume_name(cfg, volume)
        prefix = BeamFileManagerService._clean(remote_prefix)
        paths = sorted(path for path in Path(models_root).rglob("*") if path.is_file())
        items = [
            BeamUploadItem(
                local_path=path,
                remote_path="/".join(
                    part for part in (prefix, path.relative_to(models_root).as_posix()) if part
                ),
                size=path.stat().st_size,
            )
            for path in paths
        ]
        total_files = len(items)
        total_bytes = sum(item.size for item in items)
        max_workers = max(1, min(int(workers or 1), 4, total_files or 1))
        state = {
            "files_processed": 0,
            "files_uploaded": 0,
            "files_skipped": 0,
            "bytes_processed": 0,
            "bytes_uploaded": 0,
            "bytes_skipped": 0,
        }
        state_lock = threading.Lock()

        def snapshot(**extra: Any) -> dict[str, Any]:
            with state_lock:
                result = dict(state)
            result.update({
                "total": total_files,
                "bytes_total": total_bytes,
                "workers": max_workers,
                **extra,
            })
            return result

        try:
            try:
                cli_version = BeamFileManagerService._run_in_context(
                    executable=executable, env=env, args=["--version"], timeout=30
                ).strip()
            except Exception as exc:
                cli_version = f"no disponible ({exc})"
            emit(snapshot(phase="inventory", remote="", cli_version=cli_version))
            pending = items
            if not overwrite:
                parents = sorted({item.remote_path.rsplit("/", 1)[0] if "/" in item.remote_path else "" for item in items})
                inventories = {
                    parent: BeamFileManagerService._list_parent_names_in_context(
                        executable=executable, env=env, volume=selected, parent=parent
                    )
                    for parent in parents
                }
                pending = []
                for item in items:
                    parent, name = item.remote_path.rsplit("/", 1) if "/" in item.remote_path else ("", item.remote_path)
                    if name in inventories.get(parent, set()):
                        with state_lock:
                            state["files_processed"] += 1
                            state["files_skipped"] += 1
                            state["bytes_processed"] += item.size
                            state["bytes_skipped"] += item.size
                        emit(snapshot(
                            phase="file-skipped", remote=item.remote_path,
                            file_name=item.local_path.name, file_size=item.size,
                        ))
                    else:
                        pending.append(item)

            def transfer(item: BeamUploadItem) -> tuple[BeamUploadItem, str]:
                base = snapshot(
                    phase="file-start", remote=item.remote_path,
                    file_name=item.local_path.name, file_size=item.size,
                    file_bytes_transferred=0, file_bytes_total=item.size,
                )
                emit(base)
                direct_uri = BeamFileManagerService._uri(selected, item.remote_path)
                if overwrite:
                    try:
                        BeamFileManagerService._run_in_context(
                            executable=executable, env=env,
                            args=["rm", BeamFileManagerService._cli_path(selected, item.remote_path)],
                            timeout=180,
                        )
                    except BeamFileManagerError as exc:
                        if not any(marker in str(exc).casefold() for marker in (
                            "not found", "no such file", "unable to stat path", "path does not exist"
                        )):
                            raise
                try:
                    cls._stream_command(
                        executable=executable, env=env,
                        args=["cp", str(item.local_path), direct_uri],
                        timeout=timeout, item=item, emit=emit, base_event=base,
                    )
                    mode = "direct-streaming"
                except BeamFileManagerError as exc:
                    if not cls._is_nested_destination_failure(exc):
                        raise
                    emit(snapshot(
                        phase="file-fallback", remote=item.remote_path,
                        file_name=item.local_path.name, file_size=item.size,
                        detail="La CLI instalada rechazó el destino anidado; se usa raíz + mv para este archivo.",
                    ))
                    BeamFileManagerService._upload_via_root_in_context(
                        executable=executable, env=env, volume=selected,
                        local_path=item.local_path, destination=item.remote_path,
                        timeout=timeout, overwrite=overwrite,
                    )
                    mode = "root-move-fallback"
                return item, mode

            modes: set[str] = set()
            if pending:
                with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="beam-v3") as pool:
                    futures = [pool.submit(transfer, item) for item in pending]
                    for future in as_completed(futures):
                        item, mode = future.result()
                        modes.add(mode)
                        with state_lock:
                            state["files_processed"] += 1
                            state["files_uploaded"] += 1
                            state["bytes_processed"] += item.size
                            state["bytes_uploaded"] += item.size
                        emit(snapshot(
                            phase="file-completed", remote=item.remote_path,
                            file_name=item.local_path.name, file_size=item.size,
                            file_bytes_transferred=item.size, file_bytes_total=item.size,
                            transfer_mode=mode,
                        ))

            emit(snapshot(phase="completed", remote=""))
            return {
                **state,
                "files_total": total_files,
                "bytes_total": total_bytes,
                "workers": max_workers if pending else 0,
                "transfer_modes": sorted(modes),
                "volume_name": selected,
                "path": prefix,
                "cli_version": cli_version,
            }
        finally:
            shutil.rmtree(home, ignore_errors=True)
