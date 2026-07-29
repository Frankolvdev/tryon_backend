from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from app.services.beam_engine.beam_config import BeamSyncConfig


class BeamVolumeService:
    @staticmethod
    def normalize(path: str) -> str:
        clean = str(path or "").replace("\\", "/").strip("/")
        return str(PurePosixPath(clean)) if clean else ""

    @classmethod
    def remote_uri(cls, volume: str, path: str) -> str:
        normalized = cls.normalize(path)
        return f"beam://{volume}" + (f"/{normalized}" if normalized else "")

    @staticmethod
    def _sdk():
        try:
            from beta9.channel import ServiceClient
            from beta9.clients.volume import StatPathRequest
            from beta9.config import ConfigContext
        except ImportError as exc:
            raise RuntimeError("El SDK beta9 no está instalado en el entorno del backend.") from exc
        return ServiceClient, StatPathRequest, ConfigContext

    @classmethod
    def stat(cls, config: BeamSyncConfig, remote_path: str) -> dict[str, Any] | None:
        ServiceClient, StatPathRequest, ConfigContext = cls._sdk()
        clean = cls.normalize(remote_path)
        context = ConfigContext(
            token=config.api_key,
            gateway_host=config.gateway_host,
            gateway_port=config.gateway_port,
        )
        with ServiceClient(context) as client:
            response = client.volume.stat_path(
                StatPathRequest(path=f"{config.volume_name}/{clean}")
            )
            if not getattr(response, "ok", False) or getattr(response, "err_msg", ""):
                return None
            info = getattr(response, "path_info", None)
            if info is None or bool(getattr(info, "is_dir", False)):
                return None
            size = 0
            for attr in ("size", "size_bytes", "file_size"):
                value = getattr(info, attr, None)
                if value is not None:
                    size = int(value or 0)
                    break
            return {
                "path": clean,
                "size_bytes": size,
                "modified_at": getattr(info, "mod_time", None) or getattr(info, "modified_at", None),
            }

    @classmethod
    def is_identical(cls, config: BeamSyncConfig, remote_path: str, size_bytes: int) -> bool:
        metadata = cls.stat(config, remote_path)
        return bool(metadata and int(metadata.get("size_bytes") or -1) == int(size_bytes))
