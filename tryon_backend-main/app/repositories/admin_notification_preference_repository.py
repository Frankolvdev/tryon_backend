from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.admin_notification_channel import (
    AdminNotificationChannel,
)
from app.models.admin_notification_preference import (
    AdminNotificationPreference,
)


class AdminNotificationPreferenceRepository:
    def get_preference(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> AdminNotificationPreference | None:
        statement = select(
            AdminNotificationPreference
        ).where(
            AdminNotificationPreference.user_id
            == user_id
        )

        return db.execute(
            statement
        ).scalar_one_or_none()

    def list_channels(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> list[AdminNotificationChannel]:
        statement = (
            select(AdminNotificationChannel)
            .where(
                AdminNotificationChannel.user_id
                == user_id
            )
            .order_by(
                AdminNotificationChannel.channel_type
            )
        )

        return list(
            db.execute(
                statement
            ).scalars().all()
        )

    def get_channel(
        self,
        db: Session,
        *,
        user_id: int,
        channel_type: str,
    ) -> AdminNotificationChannel | None:
        statement = select(
            AdminNotificationChannel
        ).where(
            AdminNotificationChannel.user_id
            == user_id,
            AdminNotificationChannel.channel_type
            == channel_type,
        )

        return db.execute(
            statement
        ).scalar_one_or_none()

    def get_channel_by_id(
        self,
        db: Session,
        *,
        user_id: int,
        channel_id: int,
    ) -> AdminNotificationChannel | None:
        statement = select(
            AdminNotificationChannel
        ).where(
            AdminNotificationChannel.user_id
            == user_id,
            AdminNotificationChannel.id
            == channel_id,
        )

        return db.execute(
            statement
        ).scalar_one_or_none()


admin_notification_preference_repository = (
    AdminNotificationPreferenceRepository()
)