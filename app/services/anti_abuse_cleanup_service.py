from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.common.rate_limit_enums import (
    AbuseEventStatus,
)
from app.common.time import utc_now
from app.models.abuse_event import AbuseEvent
from app.models.security_block import SecurityBlock
from app.schemas.anti_abuse_operations import (
    AntiAbuseCleanupRequest,
    AntiAbuseCleanupResponse,
    AntiAbuseCleanupTaskResult,
)


class AntiAbuseCleanupService:
    def _result(
        self,
        *,
        task: str,
        processed: int,
        succeeded: int,
        failed: int,
        skipped: int,
        errors: list[dict],
    ) -> AntiAbuseCleanupTaskResult:
        return AntiAbuseCleanupTaskResult(
            task=task,
            processed=processed,
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            errors=errors,
        )

    def deactivate_expired_blocks(
        self,
        db: Session,
        *,
        limit: int,
    ) -> AntiAbuseCleanupTaskResult:
        now = utc_now()

        blocks = list(
            db.execute(
                select(SecurityBlock)
                .where(
                    SecurityBlock.is_active.is_(True),
                    SecurityBlock.is_permanent.is_(False),
                    SecurityBlock.expires_at.is_not(None),
                    SecurityBlock.expires_at <= now,
                )
                .order_by(
                    SecurityBlock.expires_at.asc()
                )
                .limit(limit)
            ).scalars().all()
        )

        succeeded = 0
        failed = 0
        skipped = 0
        errors: list[dict] = []

        for block in blocks:
            try:
                if not block.is_active:
                    skipped += 1
                    continue

                block.is_active = False

                metadata = block.metadata_json

                db.add(block)
                db.commit()
                db.refresh(block)

                succeeded += 1

            except Exception as error:
                db.rollback()
                failed += 1

                errors.append(
                    {
                        "security_block_id": block.id,
                        "error": str(error),
                    }
                )

        return self._result(
            task="deactivate_expired_blocks",
            processed=len(blocks),
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            errors=errors,
        )

    def delete_old_resolved_events(
        self,
        db: Session,
        *,
        retention_days: int,
        limit: int,
    ) -> AntiAbuseCleanupTaskResult:
        cutoff = utc_now() - timedelta(
            days=retention_days
        )

        event_ids = list(
            db.execute(
                select(AbuseEvent.id)
                .where(
                    AbuseEvent.status.in_(
                        [
                            AbuseEventStatus.RESOLVED.value,
                            AbuseEventStatus.IGNORED.value,
                        ]
                    )
                )
                .where(
                    AbuseEvent.created_at < cutoff
                )
                .order_by(
                    AbuseEvent.created_at.asc()
                )
                .limit(limit)
            ).scalars().all()
        )

        if not event_ids:
            return self._result(
                task="delete_old_resolved_events",
                processed=0,
                succeeded=0,
                failed=0,
                skipped=0,
                errors=[],
            )

        try:
            result = db.execute(
                delete(AbuseEvent).where(
                    AbuseEvent.id.in_(event_ids)
                )
            )

            db.commit()

            deleted_count = int(
                result.rowcount or 0
            )

            return self._result(
                task="delete_old_resolved_events",
                processed=len(event_ids),
                succeeded=deleted_count,
                failed=0,
                skipped=max(
                    len(event_ids) - deleted_count,
                    0,
                ),
                errors=[],
            )

        except Exception as error:
            db.rollback()

            return self._result(
                task="delete_old_resolved_events",
                processed=len(event_ids),
                succeeded=0,
                failed=len(event_ids),
                skipped=0,
                errors=[
                    {
                        "error": str(error),
                    }
                ],
            )

    def run(
        self,
        db: Session,
        *,
        options: AntiAbuseCleanupRequest,
    ) -> AntiAbuseCleanupResponse:
        started_at = utc_now()
        tasks: list[AntiAbuseCleanupTaskResult] = []

        if options.deactivate_expired_blocks:
            tasks.append(
                self.deactivate_expired_blocks(
                    db,
                    limit=options.max_items,
                )
            )

        if options.delete_old_resolved_events:
            tasks.append(
                self.delete_old_resolved_events(
                    db,
                    retention_days=(
                        options.resolved_event_retention_days
                    ),
                    limit=options.max_items,
                )
            )

        total_processed = sum(
            task.processed
            for task in tasks
        )

        total_succeeded = sum(
            task.succeeded
            for task in tasks
        )

        total_failed = sum(
            task.failed
            for task in tasks
        )

        total_skipped = sum(
            task.skipped
            for task in tasks
        )

        return AntiAbuseCleanupResponse(
            started_at=started_at,
            completed_at=utc_now(),
            tasks=tasks,
            total_processed=total_processed,
            total_succeeded=total_succeeded,
            total_failed=total_failed,
            total_skipped=total_skipped,
            success=total_failed == 0,
        )


anti_abuse_cleanup_service = AntiAbuseCleanupService()