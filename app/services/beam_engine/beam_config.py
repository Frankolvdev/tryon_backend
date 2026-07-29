from __future__ import annotations

import shutil
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.services.beam_file_manager_service import BeamFileManagerService


@dataclass(frozen=True)
class BeamSyncConfig:
    volume_name: str
    executable: str
    env: dict[str, str]
    home: str | None = None
    timeout_seconds: int = 86400
    retries: int = 3
    multipart_part_size_mb: int = 64
    multipart_workers: int = 4
    progress_interval_seconds: float = 0.25
    progress_bytes_step: int = 2 * 1024 * 1024

    @property
    def multipart_part_size_bytes(self) -> int:
        return self.multipart_part_size_mb * 1024 * 1024

    @classmethod
    def load(cls, db: Session) -> "BeamSyncConfig":
        provider, executable, env, home = BeamFileManagerService._env(db)
        volume = BeamFileManagerService._volume_name(
            provider,
            str(getattr(provider, "volume_name", "") or ""),
        )
        part_size_mb = int(
            getattr(provider, "multipart_part_size_mb", None)
            or getattr(provider, "beam_multipart_part_size_mb", None)
            or 64
        )
        workers = int(
            getattr(provider, "multipart_workers", None)
            or getattr(provider, "beam_multipart_workers", None)
            or 4
        )
        return cls(
            volume_name=volume,
            executable=str(executable),
            env=dict(env),
            home=str(home) if home else None,
            timeout_seconds=max(
                60,
                int(getattr(provider, "timeout_seconds", 86400) or 86400),
            ),
            retries=max(
                1,
                int(getattr(provider, "retries", 3) or 3),
            ),
            multipart_part_size_mb=max(8, min(512, part_size_mb)),
            multipart_workers=max(1, min(16, workers)),
        )

    def cleanup(self) -> None:
        if self.home:
            shutil.rmtree(self.home, ignore_errors=True)
