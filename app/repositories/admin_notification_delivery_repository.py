from sqlalchemy import (
    func,
    or_,
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
        status: str | None = None,
        channel_type: str | None = None,
        search: str | None = None,
    ) -> list[AdminNotificationDelivery]:
        statement = select(AdminNotificationDelivery).where(
            AdminNotificationDelivery.notification_id == notification_id
        )
        if status:
            statement = statement.where(AdminNotificationDelivery.status == status)
        if channel_type:
            statement = statement.where(AdminNotificationDelivery.channel_type == channel_type)
        if search and search.strip():
            term = f"%{search.strip()}%"
            statement = statement.where(or_(
                AdminNotificationDelivery.destination.ilike(term),
                AdminNotificationDelivery.provider_message_id.ilike(term),
                AdminNotificationDelivery.error_type.ilike(term),
                AdminNotificationDelivery.error_message.ilike(term),
            ))
        statement = (
            statement
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
        status: str | None = None,
        channel_type: str | None = None,
        search: str | None = None,
    ) -> int:
        statement = select(func.count(AdminNotificationDelivery.id)).where(
            AdminNotificationDelivery.notification_id == notification_id
        )
        if status:
            statement = statement.where(AdminNotificationDelivery.status == status)
        if channel_type:
            statement = statement.where(AdminNotificationDelivery.channel_type == channel_type)
        if search and search.strip():
            term = f"%{search.strip()}%"
            statement = statement.where(or_(
                AdminNotificationDelivery.destination.ilike(term),
                AdminNotificationDelivery.provider_message_id.ilike(term),
                AdminNotificationDelivery.error_type.ilike(term),
                AdminNotificationDelivery.error_message.ilike(term),
            ))

        return int(
            db.execute(
                statement
            ).scalar_one()
        )


admin_notification_delivery_repository = (
    AdminNotificationDeliveryRepository()
)