from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.scheduled_job_run import ScheduledJobRun
from app.repositories.base import BaseRepository


class ScheduledJobRunRepository(BaseRepository[ScheduledJobRun]):
    def __init__(self):
        super().__init__(ScheduledJobRun)

    def list_by_job_id(
        self,
        db: Session,
        scheduled_job_id: int,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ScheduledJobRun]:
        statement = (
            select(ScheduledJobRun)
            .where(ScheduledJobRun.scheduled_job_id == scheduled_job_id)
            .order_by(ScheduledJobRun.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())


scheduled_job_run_repository = ScheduledJobRunRepository()