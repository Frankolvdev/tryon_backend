from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.background_job import BackgroundJob
from app.repositories.base import BaseRepository


class BackgroundJobRepository(
    BaseRepository[BackgroundJob]
):
    def __init__(self):
        super().__init__(BackgroundJob)

    def get_by_public_id(
        self,
        db: Session,
        public_id: str,
    ) -> BackgroundJob | None:
        statement = select(
            BackgroundJob
        ).where(
            BackgroundJob.public_id
            == public_id
        )

        return db.execute(
            statement
        ).scalar_one_or_none()

    def get_by_provider_job_id(
        self,
        db: Session,
        provider_job_id: str,
    ) -> BackgroundJob | None:
        statement = (
            select(BackgroundJob)
            .where(
                BackgroundJob.provider_job_id
                == provider_job_id
            )
            .order_by(
                BackgroundJob.created_at.desc()
            )
            .limit(1)
        )

        return db.execute(
            statement
        ).scalar_one_or_none()

    def get_by_idempotency_key(
        self,
        db: Session,
        idempotency_key: str,
    ) -> BackgroundJob | None:
        statement = select(
            BackgroundJob
        ).where(
            BackgroundJob.idempotency_key
            == idempotency_key
        )

        return db.execute(
            statement
        ).scalar_one_or_none()

    def get_for_update(
        self,
        db: Session,
        job_id: int,
    ) -> BackgroundJob | None:
        statement = (
            select(BackgroundJob)
            .where(
                BackgroundJob.id == job_id
            )
            .with_for_update()
        )

        return db.execute(
            statement
        ).scalar_one_or_none()

    def list_filtered(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        queue_name: str | None = None,
        job_type: str | None = None,
        status: str | None = None,
        execution_mode: str | None = None,
        search: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[BackgroundJob]:
        statement = select(BackgroundJob)

        if user_id is not None:
            statement = statement.where(
                BackgroundJob.user_id
                == user_id
            )

        if queue_name is not None:
            statement = statement.where(
                BackgroundJob.queue_name
                == queue_name
            )

        if job_type is not None:
            statement = statement.where(
                BackgroundJob.job_type
                == job_type
            )

        if status is not None:
            statement = statement.where(
                BackgroundJob.status
                == status
            )

        if execution_mode is not None:
            statement = statement.where(
                BackgroundJob.execution_mode
                == execution_mode
            )

        if search:
            pattern = (
                f"%{search.strip()}%"
            )

            statement = statement.where(
                or_(
                    BackgroundJob.public_id.ilike(
                        pattern
                    ),
                    BackgroundJob.job_type.ilike(
                        pattern
                    ),
                    BackgroundJob.provider_job_id.ilike(
                        pattern
                    ),
                    BackgroundJob.worker_name.ilike(
                        pattern
                    ),
                )
            )

        statement = (
            statement
            .order_by(
                BackgroundJob.created_at.desc(),
                BackgroundJob.id.desc(),
            )
            .offset(skip)
            .limit(limit)
        )

        return list(
            db.execute(
                statement
            ).scalars().all()
        )

    def count_filtered(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        queue_name: str | None = None,
        job_type: str | None = None,
        status: str | None = None,
        execution_mode: str | None = None,
        search: str | None = None,
    ) -> int:
        statement = select(
            func.count(
                BackgroundJob.id
            )
        )

        if user_id is not None:
            statement = statement.where(
                BackgroundJob.user_id
                == user_id
            )

        if queue_name is not None:
            statement = statement.where(
                BackgroundJob.queue_name
                == queue_name
            )

        if job_type is not None:
            statement = statement.where(
                BackgroundJob.job_type
                == job_type
            )

        if status is not None:
            statement = statement.where(
                BackgroundJob.status
                == status
            )

        if execution_mode is not None:
            statement = statement.where(
                BackgroundJob.execution_mode
                == execution_mode
            )

        if search:
            pattern = (
                f"%{search.strip()}%"
            )

            statement = statement.where(
                or_(
                    BackgroundJob.public_id.ilike(
                        pattern
                    ),
                    BackgroundJob.job_type.ilike(
                        pattern
                    ),
                    BackgroundJob.provider_job_id.ilike(
                        pattern
                    ),
                    BackgroundJob.worker_name.ilike(
                        pattern
                    ),
                )
            )

        return int(
            db.execute(
                statement
            ).scalar_one()
        )

    def list_claimable(
        self,
        db: Session,
        *,
        queue_name: str,
        now: datetime,
        limit: int,
    ) -> list[BackgroundJob]:
        statement = (
            select(BackgroundJob)
            .where(
                BackgroundJob.queue_name
                == queue_name,
                BackgroundJob.status.in_(
                    [
                        "pending",
                        "scheduled",
                        "queued",
                        "retrying",
                    ]
                ),
                BackgroundJob.available_at
                <= now,
                or_(
                    BackgroundJob
                    .scheduled_at
                    .is_(None),
                    BackgroundJob
                    .scheduled_at
                    <= now,
                ),
                or_(
                    BackgroundJob
                    .lease_expires_at
                    .is_(None),
                    BackgroundJob
                    .lease_expires_at
                    <= now,
                ),
            )
            .order_by(
                BackgroundJob.priority.asc(),
                BackgroundJob.available_at.asc(),
                BackgroundJob.created_at.asc(),
            )
            .with_for_update(
                skip_locked=True
            )
            .limit(limit)
        )

        return list(
            db.execute(
                statement
            ).scalars().all()
        )


background_job_repository = (
    BackgroundJobRepository()
)