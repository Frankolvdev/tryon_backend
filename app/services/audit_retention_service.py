from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.common.time import utc_now
from app.models.audit_entry import AuditEntry
from app.schemas.audit_maintenance import (
    AuditRetentionRequest,
    AuditRetentionResponse,
)


class AuditRetentionService:
    def _delete_batch(
        self,
        db: Session,
        *,
        conditions: list,
        batch_size: int,
    ) -> int:
        ids = list(
            db.execute(
                select(AuditEntry.id)
                .where(*conditions)
                .order_by(
                    AuditEntry.created_at.asc(),
                    AuditEntry.id.asc(),
                )
                .limit(batch_size)
            ).scalars().all()
        )

        if not ids:
            return 0

        result = db.execute(
            delete(AuditEntry).where(
                AuditEntry.id.in_(ids)
            )
        )

        return int(
            result.rowcount or 0
        )

    def run(
        self,
        db: Session,
        *,
        data: AuditRetentionRequest,
    ) -> AuditRetentionResponse:
        started_at = utc_now()

        successful_deleted = 0
        failed_deleted = 0
        read_events_deleted = 0

        errors: list[str] = []

        successful_threshold = (
            started_at
            - timedelta(
                days=(
                    data
                    .delete_successful_older_than_days
                )
            )
        )

        failed_threshold = (
            started_at
            - timedelta(
                days=(
                    data
                    .delete_failed_older_than_days
                )
            )
        )

        read_threshold = (
            started_at
            - timedelta(
                days=(
                    data
                    .delete_read_events_older_than_days
                )
            )
        )

        try:
            conditions = [
                AuditEntry.success.is_(True),
                AuditEntry.action != "read",
                AuditEntry.created_at
                < successful_threshold,
            ]

            if data.preserve_restorable_entries:
                conditions.append(
                    AuditEntry.is_restorable.is_(
                        False
                    )
                )

            if data.preserve_restore_actions:
                conditions.append(
                    AuditEntry.action != "restore"
                )

            successful_deleted = (
                self._delete_batch(
                    db,
                    conditions=conditions,
                    batch_size=data.batch_size,
                )
            )

            db.commit()

        except Exception as error:
            db.rollback()

            errors.append(
                "successful_entries: "
                + str(error)
            )

        try:
            failed_conditions = [
                AuditEntry.success.is_(False),
                AuditEntry.created_at
                < failed_threshold,
            ]

            if data.preserve_failed_entries:
                failed_conditions.append(
                    AuditEntry.id < 0
                )

            failed_deleted = self._delete_batch(
                db,
                conditions=failed_conditions,
                batch_size=data.batch_size,
            )

            db.commit()

        except Exception as error:
            db.rollback()

            errors.append(
                "failed_entries: "
                + str(error)
            )

        try:
            read_conditions = [
                AuditEntry.action == "read",
                AuditEntry.created_at
                < read_threshold,
            ]

            if data.preserve_restorable_entries:
                read_conditions.append(
                    AuditEntry.is_restorable.is_(
                        False
                    )
                )

            read_events_deleted = (
                self._delete_batch(
                    db,
                    conditions=read_conditions,
                    batch_size=data.batch_size,
                )
            )

            db.commit()

        except Exception as error:
            db.rollback()

            errors.append(
                "read_entries: "
                + str(error)
            )

        total_deleted = (
            successful_deleted
            + failed_deleted
            + read_events_deleted
        )

        return AuditRetentionResponse(
            success=len(errors) == 0,
            successful_deleted=(
                successful_deleted
            ),
            failed_deleted=failed_deleted,
            read_events_deleted=(
                read_events_deleted
            ),
            total_deleted=total_deleted,
            started_at=started_at,
            completed_at=utc_now(),
            errors=errors,
        )


audit_retention_service = (
    AuditRetentionService()
)