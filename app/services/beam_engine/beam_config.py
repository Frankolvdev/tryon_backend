from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy.orm import Session

from app.services.beam_credentials_service import beam_credentials_service
from app.services.infrastructure_provider_service import InfrastructureProviderService


@dataclass(frozen=True)
class BeamSyncConfig:
    volume_name: str
    api_key: str
    gateway_host: str = "gateway.beam.cloud"
    gateway_port: int = 443
    timeout_seconds: int = 86400
    retries: int = 3
    multipart_part_size_mb: int = 64
    multipart_workers: int = 4
    progress_interval_seconds: float = 0.25
    progress_bytes_step: int = 2 * 1024 * 1024

    @classmethod
    def load(cls, db: Session) -> "BeamSyncConfig":
        provider = InfrastructureProviderService.get_beam(db)
        token = beam_credentials_service.normalize_token(str(provider.api_key or ""))
        if not token:
            raise RuntimeError("Configura el token de Beam antes de sincronizar modelos.")
        volume = str(provider.volume_name or "").strip().replace("\\", "/").strip("/")
        if not volume:
            raise RuntimeError("Configura el nombre del Volume de Beam.")
        return cls(
            volume_name=volume,
            api_key=token,
            timeout_seconds=max(60, int(provider.timeout_seconds or 86400)),
            retries=max(1, int(provider.retries or 3)),
        )
