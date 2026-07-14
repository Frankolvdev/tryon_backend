from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.orm import Session

from app.models.admin_notification_delivery import (
    AdminNotificationDelivery,
)


class AdminNotificationDeliveryRepository:
    def get_by_id(
        self,
        db: Session,
        *,
        delivery_id: int,
    ) -> AdminNotificationDelivery | None:
        return db.get(
            AdminNotificationDelivery,
            delivery_id,
        )

    def list_for_notification(
        self,
        db: Session,
        *,
        notification_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[AdminNotificationDelivery]:
        statement = (
            select(AdminNotificationDelivery)
            .where(
                AdminNotificationDelivery.notification_id
                == notification_id
            )
            .order_by(
                AdminNotificationDelivery.created_at.desc(),
                AdminNotificationDelivery.id.desc(),
            )
            .offset(skip)
            .limit(limit)
        )

        return list(
            db.execute(
                statement
            ).scalars().all()
        )

    def count_for_notification(
        self,
        db: Session,
        *,
        notification_id: int,
    ) -> int:
        statement = select(
            func.count(
                AdminNotificationDelivery.id
            )
        ).where(
            AdminNotificationDelivery.notification_id
            == notification_id
        )

        return int(
            db.execute(
                statement
            ).scalar_one()
        )


admin_notification_delivery_repository = (
    AdminNotificationDeliveryRepository()
)