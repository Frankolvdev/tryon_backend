from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy.orm import Session

from app.services.beam_file_manager_service import BeamFileManagerService


@dataclass(frozen=True)
class BeamSyncConfig:
    volume_name: str
    executable: str
    env: dict[str, str]
    timeout_seconds: int = 86400
    retries: int = 3

    @classmethod
    def load(cls, db: Session) -> "BeamSyncConfig":
        provider, executable, env, _home = BeamFileManagerService._env(db)
        volume = BeamFileManagerService._volume_name(provider, str(provider.get("volume_name") or ""))
        return cls(
            volume_name=volume,
            executable=str(executable),
            env=dict(env),
            timeout_seconds=max(60, int(provider.get("timeout_seconds") or 86400)),
            retries=3,
        )
