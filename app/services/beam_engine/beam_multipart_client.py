from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, TextIO

from app.services.beam_engine.beam_config import BeamSyncConfig

LineCallback = Callable[[str, dict[str, Any]], None]


class BeamMultipartClient:
    ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
    PERCENT = re.compile(r"(?P<value>[0-9]{1,3}(?:[.,][0-9]+)?)\s*%")
    SPEED = re.compile(r"(?P<value>[0-9]+(?:[.,][0-9]+)?)\s*(?P<unit>KiB|MiB|GiB|KB|MB|GB|B)/s", re.I)
    SIZE = re.compile(
        r"(?P<done>[0-9]+(?:[.,][0-9]+)?)\s*(?P<done_unit>KiB|MiB|GiB|KB|MB|GB|B)"
        r"\s*(?:/|of)\s*"
        r"(?P<total>[0-9]+(?:[.,][0-9]+)?)\s*(?P<total_unit>KiB|MiB|GiB|KB|MB|GB|B)",
        re.I,
    )
    UNITS = {"B": 1, "KB": 1000, "MB": 1000**2, "GB": 1000**3, "KIB": 1024, "MIB": 1024**2, "GIB": 1024**3}

    @classmethod
    def patch_windows_sdk(cls) -> list[str]:
        if os.name != "nt":
            return []
        patched: list[str] = []
        for base in map(Path, sys.path):
            if not base.exists():
                continue
            for path in base.glob("**/beam/**/multipart.py"):
                try:
                    text = path.read_text(encoding="utf-8")
                    updated = text.replace("os.path.join", "posixpath.join").replace("os.path.basename", "posixpath.basename")
                    if "import posixpath" not in updated:
                        updated = "import posixpath\n" + updated
                    if updated != text:
                        path.write_text(updated, encoding="utf-8")
                        patched.append(str(path))
                except OSError:
                    continue
        return patched

    @classmethod
    def _to_bytes(cls, value: str, unit: str) -> int:
        return int(float(value.replace(",", ".")) * cls.UNITS[unit.upper()])

    @classmethod
    def _metrics(cls, line: str, size: int, started: float) -> dict[str, Any]:
        clean = cls.ANSI.sub("", line).strip()
        percent_match = cls.PERCENT.search(clean)
        size_match = cls.SIZE.search(clean)
        sent = 0
        percent = 0.0
        if size_match:
            sent = min(size, cls._to_bytes(size_match.group("done"), size_match.group("done_unit")))
            percent = 100.0 * sent / max(1, size)
        elif percent_match:
            percent = float(percent_match.group("value").replace(",", "."))
            sent = int(size * min(100.0, max(0.0, percent)) / 100.0)

        speed_match = cls.SPEED.search(clean)
        speed = 0
        if speed_match:
            speed = cls._to_bytes(speed_match.group("value"), speed_match.group("unit"))
        elif sent:
            speed = int(sent / max(0.001, time.perf_counter() - started))
        eta = int((size - sent) / speed) if speed and sent < size else 0
        return {
            "native_line": clean,
            "file_progress": round(min(100.0, max(0.0, percent)), 2),
            "file_bytes_sent": sent,
            "speed_bps": speed,
            "eta_seconds": eta,
        }

    @staticmethod
    def _reader(stream: TextIO, output: queue.Queue[str]) -> None:
        """Read Rich/Beam progress frames terminated by CR or LF.

        Beam CLI does not always emit newline-delimited output. Its progress bar
        is commonly redrawn with carriage returns and may be written to stderr.
        """
        try:
            buffer = ""
            while True:
                char = stream.read(1)
                if char == "":
                    if buffer.strip():
                        output.put(buffer)
                    return
                if char in {"\r", "\n"}:
                    if buffer.strip():
                        output.put(buffer)
                    buffer = ""
                else:
                    buffer += char
        finally:
            try:
                stream.close()
            except Exception:
                pass

    @classmethod
    def upload_file(cls, config: BeamSyncConfig, source: Path, destination: str, on_line: LineCallback) -> None:
        cls.patch_windows_sdk()
        normalized_destination = destination.replace("\\", "/")
        process = subprocess.Popen(
            [config.executable, "cp", "--multipart", str(source), normalized_destination],
            env=config.env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            bufsize=0,
        )
        started = time.perf_counter()
        output: queue.Queue[str] = queue.Queue()
        assert process.stdout is not None
        assert process.stderr is not None
        readers = [
            threading.Thread(target=cls._reader, args=(process.stdout, output), daemon=True),
            threading.Thread(target=cls._reader, args=(process.stderr, output), daemon=True),
        ]
        for reader in readers:
            reader.start()

        last_emit = 0.0
        captured: list[str] = []
        try:
            while process.poll() is None or any(reader.is_alive() for reader in readers) or not output.empty():
                if time.perf_counter() - started > config.timeout_seconds:
                    process.kill()
                    raise TimeoutError(f"Beam multipart excedió {config.timeout_seconds} segundos.")
                try:
                    line = output.get(timeout=0.2)
                except queue.Empty:
                    # Heartbeat: keeps the BackOffice alive while Beam negotiates
                    # multipart before its first native progress frame.
                    now = time.perf_counter()
                    if now - last_emit >= 1.0:
                        on_line(
                            "Beam multipart activo; esperando métricas de transferencia…",
                            {
                                "native_line": "Beam multipart activo; esperando métricas de transferencia…",
                                "file_progress": 0.0,
                                "file_bytes_sent": 0,
                                "speed_bps": 0,
                                "eta_seconds": 0,
                                "elapsed_seconds": round(now - started, 1),
                            },
                        )
                        last_emit = now
                    continue
                clean = cls.ANSI.sub("", line).strip()
                if not clean:
                    continue
                captured.append(clean)
                metrics = cls._metrics(clean, source.stat().st_size, started)
                on_line(clean, metrics)
                last_emit = time.perf_counter()

            code = process.wait()
        except BaseException:
            if process.poll() is None:
                process.terminate()
            raise
        if code != 0:
            detail = "\n".join(captured[-30:])
            raise RuntimeError(f"Beam multipart terminó con código {code}. {detail}".strip())

        # Ensure the final state reaches 100% even when Beam clears its Rich bar.
        on_line(
            "Transferencia multipart completada.",
            {
                "native_line": "Transferencia multipart completada.",
                "file_progress": 100.0,
                "file_bytes_sent": source.stat().st_size,
                "speed_bps": int(source.stat().st_size / max(0.001, time.perf_counter() - started)),
                "eta_seconds": 0,
            },
        )
