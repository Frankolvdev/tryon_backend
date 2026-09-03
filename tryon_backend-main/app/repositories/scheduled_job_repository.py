from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.scheduled_job import ScheduledJob
from app.repositories.base import BaseRepository


class ScheduledJobRepository(BaseRepository[ScheduledJob]):
    def __init__(self):
        super().__init__(ScheduledJob)

    def get_by_key(self, db: Session, key: str) -> ScheduledJob | None:
        statement = select(ScheduledJob).where(ScheduledJob.key == key)
        return db.execute(statement).scalar_one_or_none()

    def list_all(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ScheduledJob]:
        statement = (
            select(ScheduledJob)
            .order_by(ScheduledJob.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())


scheduled_job_repository = ScheduledJobRepository()