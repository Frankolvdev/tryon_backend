from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.common.time import utc_now
from app.models.user_notification import (
    UserNotification,
)
from app.models.user_notification_receipt import (
    UserNotificationReceipt,
)


class UserNotificationRetentionService:
    def run(
        self,
        db: Session,
        *,
        notification_retention_days: int = 365,
        archived_receipt_retention_days: int = 90,
        batch_size: int = 1000,
    ) -> dict:
        now = utc_now()

        notification_threshold = (
            now
            - timedelta(
                days=notification_retention_days
            )
        )

        receipt_threshold = (
            now
            - timedelta(
                days=archived_receipt_retention_days
            )
        )

        notification_ids = list(
            db.execute(
                select(
                    UserNotification.id
                )
                .where(
                    UserNotification.created_at
                    < notification_threshold,
                    UserNotification.requires_action.is_(
                        False
                    ),
                    UserNotification.is_active.is_(
                        False
                    ),
                )
                .order_by(
                    UserNotification.created_at.asc()
                )
                .limit(batch_size)
            ).scalars().all()
        )

        notifications_deleted = 0

        if notification_ids:
            result = db.execute(
                delete(
                    UserNotification
                ).where(
                    UserNotification.id.in_(
                        notification_ids
                    )
                )
            )

            notifications_deleted = int(
                result.rowcount or 0
            )

        receipt_ids = list(
            db.execute(
                select(
                    UserNotificationReceipt.id
                )
                .where(
                    UserNotificationReceipt.is_archived.is_(
                        True
                    ),
                    UserNotificationReceipt.archived_at
                    < receipt_threshold,
                )
                .order_by(
                    UserNotificationReceipt.archived_at.asc()
                )
                .limit(batch_size)
            ).scalars().all()
        )

        receipts_deleted = 0

        if receipt_ids:
            result = db.execute(
                delete(
                    UserNotificationReceipt
                ).where(
                    UserNotificationReceipt.id.in_(
                        receipt_ids
                    )
                )
            )

            receipts_deleted = int(
                result.rowcount or 0
            )

        db.commit()

        return {
            "success": True,
            "notifications_deleted": (
                notifications_deleted
            ),
            "receipts_deleted": receipts_deleted,
            "total_deleted": (
                notifications_deleted
                + receipts_deleted
            ),
            "completed_at": utc_now().isoformat(),
        }


user_notification_retention_service = (
    UserNotificationRetentionService()
)