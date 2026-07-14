from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.external_ai_job import ExternalAiJob
from app.repositories.base import BaseRepository


class ExternalAiJobRepository(BaseRepository[ExternalAiJob]):
    def __init__(self):
        super().__init__(ExternalAiJob)

    def get_by_provider_job_id(
        self,
        db: Session,
        *,
        provider: str,
        provider_job_id: str,
    ) -> ExternalAiJob | None:
        statement = (
            select(ExternalAiJob)
            .where(ExternalAiJob.provider == provider)
            .where(ExternalAiJob.provider_job_id == provider_job_id)
        )
        return db.execute(statement).scalar_one_or_none()

    def list_all(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ExternalAiJob]:
        statement = (
            select(ExternalAiJob)
            .order_by(ExternalAiJob.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(db.execute(statement).scalars().all())

    def list_pending_runpod_jobs(
        self,
        db: Session,
        *,
        limit: int = 100,
    ) -> list[ExternalAiJob]:
        statement = (
            select(ExternalAiJob)
            .where(ExternalAiJob.provider == "runpod")
            .where(ExternalAiJob.provider_job_id.is_not(None))
            .where(
                ExternalAiJob.status.notin_(
                    [
                        "COMPLETED",
                        "completed",
                        "FAILED",
                        "failed",
                        "CANCELLED",
                        "cancelled",
                        "CANCELED",
                        "canceled",
                        "TIMED_OUT",
                        "timed_out",
                        "timeout",
                    ]
                )
            )
            .order_by(ExternalAiJob.created_at.asc())
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())


external_ai_job_repository = ExternalAiJobRepository()