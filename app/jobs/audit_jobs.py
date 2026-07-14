from typing import Any

from sqlalchemy.orm import Session

from app.schemas.audit_maintenance import (
    AuditRetentionRequest,
)
from app.services.audit_retention_service import (
    audit_retention_service,
)
from app.services.audit_self_test_service import (
    audit_self_test_service,
)
from app.services.audit_statistics_service import (
    audit_statistics_service,
)


def audit_retention_handler(
    db: Session,
    *,
    delete_successful_older_than_days: int = 365,
    delete_failed_older_than_days: int = 730,
    delete_read_events_older_than_days: int = 90,
    preserve_restorable_entries: bool = True,
    preserve_restore_actions: bool = True,
    preserve_failed_entries: bool = True,
    batch_size: int = 1000,
    **kwargs,
) -> dict[str, Any]:
    del kwargs

    result = audit_retention_service.run(
        db,
        data=AuditRetentionRequest(
            delete_successful_older_than_days=(
                delete_successful_older_than_days
            ),
            delete_failed_older_than_days=(
                delete_failed_older_than_days
            ),
            delete_read_events_older_than_days=(
                delete_read_events_older_than_days
            ),
            preserve_restorable_entries=(
                preserve_restorable_entries
            ),
            preserve_restore_actions=(
                preserve_restore_actions
            ),
            preserve_failed_entries=(
                preserve_failed_entries
            ),
            batch_size=batch_size,
        ),
    )

    return {
        "success": result.success,
        "result": result.model_dump(
            mode="json"
        ),
    }


def audit_statistics_handler(
    db: Session,
    *,
    period_days: int = 30,
    top_limit: int = 10,
    **kwargs,
) -> dict[str, Any]:
    del kwargs

    result = (
        audit_statistics_service
        .advanced_statistics(
            db,
            period_days=period_days,
            top_limit=top_limit,
        )
    )

    return {
        "success": True,
        "statistics": result.model_dump(
            mode="json"
        ),
    }


def audit_self_test_handler(
    db: Session,
    **kwargs,
) -> dict[str, Any]:
    del db
    del kwargs

    result = audit_self_test_service.run()

    return {
        "success": result.success,
        "result": result.model_dump(
            mode="json"
        ),
    }


AUDIT_JOB_HANDLERS = {
    "audit.retention": (
        audit_retention_handler
    ),
    "audit.statistics": (
        audit_statistics_handler
    ),
    "audit.self_test": (
        audit_self_test_handler
    ),
}