from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from app.services.beam_engine.beam_config import BeamSyncConfig

LineCallback = Callable[[str, dict[str, Any]], None]


class BeamMultipartClient:
    ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
    PERCENT = re.compile(r"(?P<value>[0-9]{1,3}(?:[.,][0-9]+)?)\s*%")
    SPEED = re.compile(r"(?P<value>[0-9]+(?:[.,][0-9]+)?)\s*(?P<unit>KiB|MiB|GiB|KB|MB|GB|B)/s", re.I)
    UNITS = {"B":1,"KB":1000,"MB":1000**2,"GB":1000**3,"KIB":1024,"MIB":1024**2,"GIB":1024**3}

    @classmethod
    def patch_windows_sdk(cls) -> list[str]:
        if os.name != "nt":
            return []
        patched=[]
        for base in map(Path, sys.path):
            if not base.exists():
                continue
            for path in base.glob("**/beam/**/multipart.py"):
                try:
                    text=path.read_text(encoding="utf-8")
                    updated=text.replace("os.path.join", "posixpath.join").replace("os.path.basename", "posixpath.basename")
                    if "import posixpath" not in updated:
                        updated="import posixpath\n"+updated
                    if updated != text:
                        path.write_text(updated, encoding="utf-8")
                        patched.append(str(path))
                except OSError:
                    continue
        return patched

    @classmethod
    def _metrics(cls, line: str, size: int, started: float) -> dict[str, Any]:
        clean=cls.ANSI.sub("", line).strip()
        percent_match=cls.PERCENT.search(clean)
        percent=float(percent_match.group("value").replace(",", ".")) if percent_match else 0.0
        sent=int(size*min(100.0,max(0.0,percent))/100.0)
        speed_match=cls.SPEED.search(clean)
        speed=0
        if speed_match:
            speed=int(float(speed_match.group("value").replace(",", "."))*cls.UNITS[speed_match.group("unit").upper()])
        elif sent:
            speed=int(sent/max(.001,time.perf_counter()-started))
        eta=int((size-sent)/speed) if speed and sent < size else 0
        return {"native_line":clean,"file_progress":round(percent,2),"file_bytes_sent":sent,"speed_bps":speed,"eta_seconds":eta}

    @classmethod
    def upload_file(cls, config: BeamSyncConfig, source: Path, destination: str, on_line: LineCallback) -> None:
        cls.patch_windows_sdk()
        normalized_destination=destination.replace("\\", "/")
        process=subprocess.Popen(
            [config.executable, "cp", str(source), normalized_destination],
            env=config.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        started=time.perf_counter()
        assert process.stdout is not None
        try:
            for line in iter(process.stdout.readline, ""):
                on_line(line, cls._metrics(line, source.stat().st_size, started))
            code=process.wait(timeout=config.timeout_seconds)
        except BaseException:
            process.terminate()
            raise
        if code != 0:
            raise RuntimeError(f"Beam multipart terminó con código {code}.")
