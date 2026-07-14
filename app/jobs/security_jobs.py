from collections.abc import Callable

from sqlalchemy.orm import Session

from app.common.time import utc_now
from app.schemas.anti_abuse_operations import (
    AntiAbuseCleanupRequest,
    AntiAbuseJobResult,
)
from app.services.anti_abuse_cleanup_service import (
    anti_abuse_cleanup_service,
)


class SecurityJobs:
    def cleanup_expired_blocks(
        self,
        db: Session,
        *,
        max_items: int = 1000,
    ) -> AntiAbuseJobResult:
        started_at = utc_now()

        cleanup = (
            anti_abuse_cleanup_service
            .deactivate_expired_blocks(
                db,
                limit=max_items,
            )
        )

        return AntiAbuseJobResult(
            job_name="security.cleanup_expired_blocks",
            started_at=started_at,
            completed_at=utc_now(),
            processed=cleanup.processed,
            succeeded=cleanup.succeeded,
            failed=cleanup.failed,
            skipped=cleanup.skipped,
            success=cleanup.failed == 0,
            errors=cleanup.errors,
        )

    def cleanup_old_events(
        self,
        db: Session,
        *,
        max_items: int = 1000,
    ) -> AntiAbuseJobResult:
        started_at = utc_now()

        cleanup = (
            anti_abuse_cleanup_service
            .delete_old_resolved_events(
                db,
                retention_days=180,
                limit=max_items,
            )
        )

        return AntiAbuseJobResult(
            job_name="security.cleanup_old_events",
            started_at=started_at,
            completed_at=utc_now(),
            processed=cleanup.processed,
            succeeded=cleanup.succeeded,
            failed=cleanup.failed,
            skipped=cleanup.skipped,
            success=cleanup.failed == 0,
            errors=cleanup.errors,
        )

    def daily_maintenance(
        self,
        db: Session,
        *,
        max_items: int = 1000,
    ) -> AntiAbuseJobResult:
        started_at = utc_now()

        cleanup = anti_abuse_cleanup_service.run(
            db,
            options=AntiAbuseCleanupRequest(
                deactivate_expired_blocks=True,
                delete_old_resolved_events=False,
                resolved_event_retention_days=180,
                max_items=max_items,
            ),
        )

        return AntiAbuseJobResult(
            job_name="security.daily_maintenance",
            started_at=started_at,
            completed_at=utc_now(),
            processed=cleanup.total_processed,
            succeeded=cleanup.total_succeeded,
            failed=cleanup.total_failed,
            skipped=cleanup.total_skipped,
            success=cleanup.success,
            errors=[
                error
                for task in cleanup.tasks
                for error in task.errors
            ],
        )


security_jobs = SecurityJobs()


SECURITY_JOB_HANDLERS: dict[
    str,
    Callable[..., AntiAbuseJobResult],
] = {
    "security.cleanup_expired_blocks": (
        security_jobs.cleanup_expired_blocks
    ),
    "security.cleanup_old_events": (
        security_jobs.cleanup_old_events
    ),
    "security.daily_maintenance": (
        security_jobs.daily_maintenance
    ),
}