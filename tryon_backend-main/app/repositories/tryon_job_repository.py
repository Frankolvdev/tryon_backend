from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import TryOnJobStatus
from app.models.tryon_job import TryOnJob
from app.repositories.base import BaseRepository


class TryOnJobRepository(BaseRepository[TryOnJob]):
    def __init__(self):
        super().__init__(TryOnJob)

    def list_by_user_id(
        self,
        db: Session,
        user_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> list[TryOnJob]:
        statement = (
            select(TryOnJob)
            .where(TryOnJob.user_id == user_id)
            .order_by(TryOnJob.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())

    def list_all(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> list[TryOnJob]:
        statement = (
            select(TryOnJob)
            .order_by(TryOnJob.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())

    def count_all(self, db: Session) -> int:
        statement = select(func.count()).select_from(TryOnJob)
        return int(db.execute(statement).scalar_one())

    def count_by_status(self, db: Session, status: TryOnJobStatus) -> int:
        statement = (
            select(func.count())
            .select_from(TryOnJob)
            .where(TryOnJob.status == status.value)
        )
        return int(db.execute(statement).scalar_one())

    def sum_estimated_gpu_cost_cents(self, db: Session) -> int:
        statement = select(func.coalesce(func.sum(TryOnJob.estimated_gpu_cost_cents), 0))
        return int(db.execute(statement).scalar_one())

    def sum_actual_gpu_cost_cents(self, db: Session) -> int:
        statement = select(func.coalesce(func.sum(TryOnJob.actual_gpu_cost_cents), 0))
        return int(db.execute(statement).scalar_one())


tryon_job_repository = TryOnJobRepository()