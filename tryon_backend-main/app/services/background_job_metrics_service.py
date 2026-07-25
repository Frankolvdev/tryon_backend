from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.job_enums import JobStatus
from app.common.time import utc_now
from app.models.background_job import BackgroundJob
from app.models.background_job_attempt import (
    BackgroundJobAttempt,
)
from app.schemas.background_job_operations import (
    BackgroundJobMetricsResponse,
    ExecutionModeMetric,
    QueueNameMetric,
    QueueStatusMetric,
)


class BackgroundJobMetricsService:
    def _period(
        self,
        *,
        start: datetime | None,
        end: datetime | None,
    ) -> tuple[datetime, datetime]:
        resolved_end = end or utc_now()
        resolved_start = (
            start
            or resolved_end - timedelta(days=30)
        )

        if resolved_start >= resolved_end:
            raise ValueError(
                "start must be earlier than end."
            )

        return resolved_start, resolved_end

    def _count(
        self,
        db: Session,
        *,
        start: datetime,
        end: datetime,
        status: str | None = None,
    ) -> int:
        statement = select(
            func.count(
                BackgroundJob.id
            )
        ).where(
            BackgroundJob.created_at >= start,
            BackgroundJob.created_at < end,
        )

        if status is not None:
            statement = statement.where(
                BackgroundJob.status == status
            )

        return int(
            db.execute(
                statement
            ).scalar_one()
        )

    def get_metrics(
        self,
        db: Session,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> BackgroundJobMetricsResponse:
        period_start, period_end = (
            self._period(
                start=start,
                end=end,
            )
        )

        now = utc_now()

        status_rows = db.execute(
            select(
                BackgroundJob.status,
                func.count(
                    BackgroundJob.id
                ),
            )
            .where(
                BackgroundJob.created_at
                >= period_start,
                BackgroundJob.created_at
                < period_end,
            )
            .group_by(
                BackgroundJob.status
            )
        ).all()

        queue_rows = db.execute(
            select(
                BackgroundJob.queue_name,
                func.count(
                    BackgroundJob.id
                ),
            )
            .where(
                BackgroundJob.created_at
                >= period_start,
                BackgroundJob.created_at
                < period_end,
            )
            .group_by(
                BackgroundJob.queue_name
            )
        ).all()

        mode_rows = db.execute(
            select(
                BackgroundJob.execution_mode,
                func.count(
                    BackgroundJob.id
                ),
            )
            .where(
                BackgroundJob.created_at
                >= period_start,
                BackgroundJob.created_at
                < period_end,
            )
            .group_by(
                BackgroundJob.execution_mode
            )
        ).all()

        expired_leases = int(
            db.execute(
                select(
                    func.count(
                        BackgroundJob.id
                    )
                ).where(
                    BackgroundJob.status.in_(
                        [
                            JobStatus.CLAIMED.value,
                            JobStatus.RUNNING.value,
                            JobStatus
                            .CANCEL_REQUESTED
                            .value,
                        ]
                    ),
                    BackgroundJob
                    .lease_expires_at
                    .is_not(None),
                    BackgroundJob
                    .lease_expires_at
                    <= now,
                )
            ).scalar_one()
        )

        average_duration = db.execute(
            select(
                func.avg(
                    BackgroundJobAttempt
                    .duration_seconds
                )
            ).where(
                BackgroundJobAttempt.created_at
                >= period_start,
                BackgroundJobAttempt.created_at
                < period_end,
            )
        ).scalar_one()

        average_attempts = db.execute(
            select(
                func.avg(
                    BackgroundJob.attempt_count
                )
            ).where(
                BackgroundJob.created_at
                >= period_start,
                BackgroundJob.created_at
                < period_end,
            )
        ).scalar_one()

        return BackgroundJobMetricsResponse(
            total_jobs=self._count(
                db,
                start=period_start,
                end=period_end,
            ),
            queued_jobs=self._count(
                db,
                start=period_start,
                end=period_end,
                status=JobStatus.QUEUED.value,
            ),
            running_jobs=self._count(
                db,
                start=period_start,
                end=period_end,
                status=JobStatus.RUNNING.value,
            ),
            succeeded_jobs=self._count(
                db,
                start=period_start,
                end=period_end,
                status=JobStatus.SUCCEEDED.value,
            ),
            failed_jobs=self._count(
                db,
                start=period_start,
                end=period_end,
                status=JobStatus.FAILED.value,
            ),
            retrying_jobs=self._count(
                db,
                start=period_start,
                end=period_end,
                status=JobStatus.RETRYING.value,
            ),
            dead_letter_jobs=self._count(
                db,
                start=period_start,
                end=period_end,
                status=JobStatus.DEAD_LETTER.value,
            ),
            canceled_jobs=self._count(
                db,
                start=period_start,
                end=period_end,
                status=JobStatus.CANCELED.value,
            ),
            expired_leases=expired_leases,
            average_duration_seconds=(
                float(average_duration)
                if average_duration is not None
                else None
            ),
            average_attempts=(
                float(average_attempts)
                if average_attempts is not None
                else None
            ),
            jobs_by_status=[
                QueueStatusMetric(
                    status=str(status),
                    total=int(total),
                )
                for status, total in status_rows
            ],
            jobs_by_queue=[
                QueueNameMetric(
                    queue_name=str(queue_name),
                    total=int(total),
                )
                for queue_name, total in queue_rows
            ],
            jobs_by_execution_mode=[
                ExecutionModeMetric(
                    execution_mode=str(mode),
                    total=int(total),
                )
                for mode, total in mode_rows
            ],
            period_start=period_start,
            period_end=period_end,
            generated_at=utc_now(),
        )


background_job_metrics_service = (
    BackgroundJobMetricsService()
)