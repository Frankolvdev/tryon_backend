from typing import Any

from sqlalchemy.orm import Session

from app.services.user_notification_retention_service import (
    user_notification_retention_service,
)


def user_notification_retention_handler(
    db: Session,
    *,
    notification_retention_days: int = 365,
    archived_receipt_retention_days: int = 90,
    batch_size: int = 1000,
    **kwargs,
) -> dict[str, Any]:
    del kwargs

    return (
        user_notification_retention_service
        .run(
            db,
            notification_retention_days=(
                notification_retention_days
            ),
            archived_receipt_retention_days=(
                archived_receipt_retention_days
            ),
            batch_size=batch_size,
        )
    )


USER_NOTIFICATION_JOB_HANDLERS = {
    "user_notifications.retention": (
        user_notification_retention_handler
    ),
}