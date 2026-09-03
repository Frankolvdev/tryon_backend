from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from app.common.job_enums import JobStatus
from app.common.time import utc_now
from app.models.background_job import BackgroundJob
from app.schemas.background_job_operations import (
    BackgroundJobMaintenanceRequest,
    BackgroundJobMaintenanceResponse,
)
from app.services.background_job_claim_service import (
    background_job_claim_service,
)
from app.services.background_job_redis_service import (
    background_job_redis_service,
)


class BackgroundJobMaintenanceService:
    def run(
        self,
        db: Session,
        *,
        data: BackgroundJobMaintenanceRequest,
    ) -> BackgroundJobMaintenanceResponse:
        started_at = utc_now()

        inspected = 0
        recovered = 0
        dead_lettered = 0
        signaled_queues: list[str] = []
        errors: list[dict] = []

        if data.recover_expired_leases:
            try:
                result = (
                    background_job_claim_service
                    .recover_expired_leases(
                        db,
                        limit=data.max_items,
                    )
                )

                inspected = result.inspected
                recovered = result.recovered
                dead_lettered = (
                    result.dead_lettered
                )

                errors.extend(result.errors)

            except Exception as error:
                db.rollback()

                errors.append(
                    {
                        "task": (
                            "recover_expired_leases"
                        ),
                        "error": str(error),
                    }
                )

        if data.signal_ready_queues:
            try:
                now = utc_now()

                queue_names = list(
                    db.execute(
                        select(
                            distinct(
                                BackgroundJob.queue_name
                            )
                        ).where(
                            BackgroundJob.status.in_(
                                [
                                    JobStatus.PENDING.value,
                                    JobStatus.SCHEDULED.value,
                                    JobStatus.QUEUED.value,
                                    JobStatus.RETRYING.value,
                                ]
                            ),
                            BackgroundJob.available_at
                            <= now,
                        )
                    ).scalars().all()
                )

                for queue_name in queue_names:
                    signaled = (
                        background_job_redis_service
                        .notify_queue(
                            queue_name=queue_name,
                        )
                    )

                    if signaled:
                        signaled_queues.append(
                            queue_name
                        )

            except Exception as error:
                errors.append(
                    {
                        "task": (
                            "signal_ready_queues"
                        ),
                        "error": str(error),
                    }
                )

        return BackgroundJobMaintenanceResponse(
            success=len(errors) == 0,
            expired_leases_inspected=inspected,
            recovered_jobs=recovered,
            dead_lettered_jobs=dead_lettered,
            signaled_queues=signaled_queues,
            errors=errors,
            started_at=started_at,
            completed_at=utc_now(),
        )


background_job_maintenance_service = (
    BackgroundJobMaintenanceService()
)