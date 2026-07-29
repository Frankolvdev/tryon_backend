from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

import requests

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
            from beta9.clients.volume import (
                CreatePresignedUrlRequest,
                PresignedUrlMethod,
                StatPathRequest,
            )
            from beta9.config import ConfigContext
        except ImportError as exc:
            raise RuntimeError("El SDK beta9 no está instalado en el entorno del backend.") from exc
        return {
            "ServiceClient": ServiceClient,
            "ConfigContext": ConfigContext,
            "CreatePresignedUrlRequest": CreatePresignedUrlRequest,
            "PresignedUrlMethod": PresignedUrlMethod,
            "StatPathRequest": StatPathRequest,
        }

    @classmethod
    def stat(cls, config: BeamSyncConfig, remote_path: str) -> dict[str, Any] | None:
        """Consulta el objeto exacto mediante SDK + HEAD prefirmado.

        `beam ls` no participa. HEAD entrega el Content-Length real del objeto y
        evita depender de campos variables de PathInfo entre versiones beta9.
        """
        sdk = cls._sdk()
        clean = cls.normalize(remote_path)
        if not clean:
            return None
        context = sdk["ConfigContext"](
            token=config.api_key,
            gateway_host=config.gateway_host,
            gateway_port=config.gateway_port,
        )
        with sdk["ServiceClient"](context) as client:
            try:
                presigned = client.volume.create_presigned_url(
                    sdk["CreatePresignedUrlRequest"](
                        volume_name=config.volume_name,
                        volume_path=clean,
                        expires=60,
                        method=sdk["PresignedUrlMethod"].HeadObject,
                    )
                )
                if getattr(presigned, "ok", False) and getattr(presigned, "url", ""):
                    response = requests.head(
                        str(presigned.url),
                        allow_redirects=True,
                        timeout=(15, 60),
                    )
                    if response.status_code == 200:
                        return {
                            "path": clean,
                            "size_bytes": int(response.headers.get("Content-Length") or 0),
                            "etag": str(response.headers.get("ETag") or "").strip('"'),
                            "last_modified": response.headers.get("Last-Modified"),
                            "source": "beta9-presigned-head",
                        }
                    if response.status_code in (403, 404):
                        return None
            except Exception:
                # Compatibilidad con versiones donde HeadObject no esté expuesto.
                pass

            response = client.volume.stat_path(
                sdk["StatPathRequest"](path=f"{config.volume_name}/{clean}")
            )
            if not getattr(response, "ok", False) or getattr(response, "err_msg", ""):
                return None
            info = getattr(response, "path_info", None)
            if info is None or bool(getattr(info, "is_dir", False)):
                return None
            size = None
            for attr in ("size", "size_bytes", "file_size", "content_length"):
                value = getattr(info, attr, None)
                if value is not None:
                    size = int(value or 0)
                    break
            if size is None:
                return None
            return {
                "path": clean,
                "size_bytes": size,
                "modified_at": getattr(info, "mod_time", None)
                or getattr(info, "modified_at", None),
                "source": "beta9-stat-path",
            }

    @classmethod
    def identical_metadata(
        cls, config: BeamSyncConfig, remote_path: str, size_bytes: int
    ) -> dict[str, Any] | None:
        metadata = cls.stat(config, remote_path)
        if not metadata:
            return None
        if int(metadata.get("size_bytes") or -1) != int(size_bytes):
            return None
        return metadata

    @classmethod
    def is_identical(cls, config: BeamSyncConfig, remote_path: str, size_bytes: int) -> bool:
        return cls.identical_metadata(config, remote_path, size_bytes) is not None
