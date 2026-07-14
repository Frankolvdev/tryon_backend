from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.runpod_config import RunPodConfig
from app.repositories.base import BaseRepository


class RunPodConfigRepository(BaseRepository[RunPodConfig]):
    def __init__(self):
        super().__init__(RunPodConfig)

    def get_active(self, db: Session) -> RunPodConfig | None:
        statement = (
            select(RunPodConfig)
            .where(RunPodConfig.is_active.is_(True))
            .order_by(RunPodConfig.id.desc())
        )

        return db.execute(statement).scalars().first()

    def list_all(self, db: Session) -> list[RunPodConfig]:
        statement = select(RunPodConfig).order_by(RunPodConfig.id.desc())
        return list(db.execute(statement).scalars().all())


runpod_config_repository = RunPodConfigRepository()