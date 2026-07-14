
from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.common.time import utc_now
from app.models.operational_event import (
    OperationalEvent,
)
from app.schemas.observability_maintenance import (
    OperationalEventRetentionRequest,
    OperationalEventRetentionResponse,
)
from app.services.operational_event_service import (
    operational_event_service,
)


class OperationalEventRetentionService:
    def _delete_limited(
        self,
        db: Session,
        *,
        conditions: list,
        batch_size: int,
    ) -> int:
        ids = list(
            db.query(OperationalEvent.id)
            .filter(*conditions)
            .order_by(
                OperationalEvent.created_at.asc()
            )
            .limit(batch_size)
            .scalars()
            .all()
        )

        if not ids:
            return 0

        result = db.execute(
            delete(OperationalEvent).where(
                OperationalEvent.id.in_(ids)
            )
        )

        return int(
            result.rowcount or 0
        )

    def run(
        self,
        db: Session,
        *,
        data: OperationalEventRetentionRequest,
    ) -> OperationalEventRetentionResponse:
        started_at = utc_now()

        resolved_deleted = 0
        info_deleted = 0
        warnings_deleted = 0
        errors_deleted = 0

        errors: list[str] = []

        try:
            resolved_threshold = (
                started_at
                - timedelta(
                    days=(
                        data
                        .delete_resolved_older_than_days
                    )
                )
            )

            resolved_deleted = self._delete_limited(
                db,
                conditions=[
                    OperationalEvent.is_resolved.is_(
                        True
                    ),
                    OperationalEvent.created_at
                    < resolved_threshold,
                ],
                batch_size=data.batch_size,
            )

            db.commit()

        except Exception as error:
            db.rollback()
            errors.append(
                "resolved_events: "
                + str(error)
            )

        try:
            info_threshold = (
                started_at
                - timedelta(
                    days=(
                        data
                        .delete_info_older_than_days
                    )
                )
            )

            info_deleted = self._delete_limited(
                db,
                conditions=[
                    OperationalEvent.severity
                    == "info",
                    OperationalEvent.created_at
                    < info_threshold,
                ],
                batch_size=data.batch_size,
            )

            db.commit()

        except Exception as error:
            db.rollback()
            errors.append(
                "info_events: "
                + str(error)
            )

        try:
            warning_threshold = (
                started_at
                - timedelta(
                    days=(
                        data
                        .delete_warning_older_than_days
                    )
                )
            )

            warning_conditions = [
                OperationalEvent.severity
                == "warning",
                OperationalEvent.created_at
                < warning_threshold,
            ]

            warnings_deleted = self._delete_limited(
                db,
                conditions=warning_conditions,
                batch_size=data.batch_size,
            )

            db.commit()

        except Exception as error:
            db.rollback()
            errors.append(
                "warning_events: "
                + str(error)
            )

        try:
            error_threshold = (
                started_at
                - timedelta(
                    days=(
                        data
                        .delete_error_older_than_days
                    )
                )
            )

            error_conditions = [
                OperationalEvent.severity.in_(
                    [
                        "error",
                        "critical",
                    ]
                ),
                OperationalEvent.created_at
                < error_threshold,
            ]

            if data.preserve_unresolved_errors:
                error_conditions.append(
                    ~(
                        (
                            OperationalEvent.severity
                            == "error"
                        )
                        &
                        (
                            OperationalEvent
                            .is_resolved
                            .is_(False)
                        )
                    )
                )

            if data.preserve_unresolved_critical:
                error_conditions.append(
                    ~(
                        (
                            OperationalEvent.severity
                            == "critical"
                        )
                        &
                        (
                            OperationalEvent
                            .is_resolved
                            .is_(False)
                        )
                    )
                )

            errors_deleted = self._delete_limited(
                db,
                conditions=error_conditions,
                batch_size=data.batch_size,
            )

            db.commit()

        except Exception as error:
            db.rollback()
            errors.append(
                "error_events: "
                + str(error)
            )

        try:
            operational_event_service.refresh_unresolved_metrics(
                db
            )

        except Exception as error:
            errors.append(
                "refresh_metrics: "
                + str(error)
            )

        total_deleted = (
            resolved_deleted
            + info_deleted
            + warnings_deleted
            + errors_deleted
        )

        return OperationalEventRetentionResponse(
            success=len(errors) == 0,
            resolved_deleted=resolved_deleted,
            info_deleted=info_deleted,
            warnings_deleted=warnings_deleted,
            errors_deleted=errors_deleted,
            total_deleted=total_deleted,
            started_at=started_at,
            completed_at=utc_now(),
            errors=errors,
        )


operational_event_retention_service = (
    OperationalEventRetentionService()
)