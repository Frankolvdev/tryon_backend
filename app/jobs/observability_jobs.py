from typing import Any

from sqlalchemy.orm import Session

from app.schemas.observability_maintenance import (
    OperationalEventRetentionRequest,
)
from app.services.observability_self_test_service import (
    observability_self_test_service,
)
from app.services.operational_event_retention_service import (
    operational_event_retention_service,
)
from app.services.operational_event_service import (
    operational_event_service,
)


def operational_event_retention_handler(
    db: Session,
    *,
    delete_resolved_older_than_days: int = 30,
    delete_info_older_than_days: int = 14,
    delete_warning_older_than_days: int = 90,
    delete_error_older_than_days: int = 365,
    preserve_unresolved_errors: bool = True,
    preserve_unresolved_critical: bool = True,
    batch_size: int = 1000,
    **kwargs,
) -> dict[str, Any]:
    del kwargs

    result = (
        operational_event_retention_service
        .run(
            db,
            data=OperationalEventRetentionRequest(
                delete_resolved_older_than_days=(
                    delete_resolved_older_than_days
                ),
                delete_info_older_than_days=(
                    delete_info_older_than_days
                ),
                delete_warning_older_than_days=(
                    delete_warning_older_than_days
                ),
                delete_error_older_than_days=(
                    delete_error_older_than_days
                ),
                preserve_unresolved_errors=(
                    preserve_unresolved_errors
                ),
                preserve_unresolved_critical=(
                    preserve_unresolved_critical
                ),
                batch_size=batch_size,
            ),
        )
    )

    return {
        "success": result.success,
        "result": result.model_dump(
            mode="json"
        ),
    }


def operational_event_metrics_handler(
    db: Session,
    **kwargs,
) -> dict[str, Any]:
    del kwargs

    operational_event_service.refresh_unresolved_metrics(
        db
    )

    summary = operational_event_service.summary(
        db
    )

    return {
        "success": True,
        "summary": summary.model_dump(
            mode="json"
        ),
    }


def observability_self_test_handler(
    db: Session,
    **kwargs,
) -> dict[str, Any]:
    del kwargs

    result = (
        observability_self_test_service
        .run(db)
    )

    return {
        "success": result.success,
        "result": result.model_dump(
            mode="json"
        ),
    }


OBSERVABILITY_JOB_HANDLERS = {
    "observability.operational_event_retention": (
        operational_event_retention_handler
    ),
    "observability.refresh_event_metrics": (
        operational_event_metrics_handler
    ),
    "observability.self_test": (
        observability_self_test_handler
    ),
}