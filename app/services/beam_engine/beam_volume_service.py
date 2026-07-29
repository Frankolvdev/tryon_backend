from __future__ import annotations

import json
import subprocess
from pathlib import PurePosixPath
from typing import Any

from app.services.beam_engine.beam_config import BeamSyncConfig


class BeamVolumeService:
    @staticmethod
    def normalize(path: str) -> str:
        return str(PurePosixPath(path.replace("\\", "/").strip("/"))) if path.strip("/\\") else ""

    @classmethod
    def remote_uri(cls, volume: str, path: str) -> str:
        normalized = cls.normalize(path)
        return f"beam://{volume}" + (f"/{normalized}" if normalized else "")

    @classmethod
    def list_volume(cls, config: BeamSyncConfig) -> str:
        # Beam valida `beam ls <volume>`, no `beam ls beam://<volume>`.
        completed = subprocess.run(
            [config.executable, "ls", config.volume_name],
            env=config.env, capture_output=True, text=True, timeout=120, check=False,
        )
        return (completed.stdout or "") + "\n" + (completed.stderr or "")

    @classmethod
    def metadata_index(cls, config: BeamSyncConfig) -> dict[str, dict[str, Any]]:
        text = cls.list_volume(config)
        result: dict[str, dict[str, Any]] = {}
        for line in text.splitlines():
            clean = line.strip().replace("\\", "/")
            if not clean or clean.lower().startswith(("name", "path", "total")):
                continue
            parts = clean.split()
            candidate = next((part for part in parts if "/" in part or "." in part), "")
            if candidate:
                result[candidate.strip("/")] = {"raw": clean}
        return result
