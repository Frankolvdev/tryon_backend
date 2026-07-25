from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.background_job_attempt import (
    BackgroundJobAttempt,
)
from app.repositories.base import BaseRepository


class BackgroundJobAttemptRepository(
    BaseRepository[BackgroundJobAttempt]
):
    def __init__(self):
        super().__init__(BackgroundJobAttempt)

    def list_by_job_id(
        self,
        db: Session,
        *,
        background_job_id: int,
    ) -> list[BackgroundJobAttempt]:
        statement = (
            select(BackgroundJobAttempt)
            .where(
                BackgroundJobAttempt.background_job_id
                == background_job_id
            )
            .order_by(
                BackgroundJobAttempt.attempt_number.asc()
            )
        )

        return list(
            db.execute(statement).scalars().all()
        )

    def count_by_job_id(
        self,
        db: Session,
        *,
        background_job_id: int,
    ) -> int:
        statement = (
            select(
                func.count(
                    BackgroundJobAttempt.id
                )
            )
            .where(
                BackgroundJobAttempt.background_job_id
                == background_job_id
            )
        )

        return int(db.execute(statement).scalar_one())

    def get_latest_for_job(
        self,
        db: Session,
        *,
        background_job_id: int,
    ) -> BackgroundJobAttempt | None:
        statement = (
            select(BackgroundJobAttempt)
            .where(
                BackgroundJobAttempt.background_job_id
                == background_job_id
            )
            .order_by(
                BackgroundJobAttempt.attempt_number.desc()
            )
            .limit(1)
        )

        return db.execute(statement).scalar_one_or_none()


background_job_attempt_repository = (
    BackgroundJobAttemptRepository()
)