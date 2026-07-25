from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.services.localized_message_service import (
    localized_message_service,
)
from app.services.user_notification_service import (
    user_notification_service,
)


class LocalizedUserNotificationService:
    def create_for_user(
        self,
        db: Session,
        *,
        user_id: int,
        title_key: str,
        message_key: str,
        title_variables: dict[str, Any] | None = None,
        message_variables: dict[str, Any] | None = None,
        title_default: str | None = None,
        message_default: str | None = None,
        notification_type: str = "info",
        priority: str = "normal",
        source: str = "system",
        event_type: str | None = None,
        action_url: str | None = None,
        action_label_key: str | None = None,
        action_label_default: str | None = None,
        entity_type: str | None = None,
        entity_id: str | int | None = None,
        image_url: str | None = None,
        metadata: dict[str, Any] | None = None,
        requires_action: bool = False,
        expires_at: datetime | None = None,
    ):
        title = (
            localized_message_service
            .for_user(
                db,
                user_id=user_id,
                translation_key=(
                    title_key
                ),
                variables=(
                    title_variables
                ),
                default=(
                    title_default
                ),
            )
        )

        message = (
            localized_message_service
            .for_user(
                db,
                user_id=user_id,
                translation_key=(
                    message_key
                ),
                variables=(
                    message_variables
                ),
                default=(
                    message_default
                ),
            )
        )

        action_label = None

        if action_label_key:
            action_label = (
                localized_message_service
                .for_user(
                    db,
                    user_id=user_id,
                    translation_key=(
                        action_label_key
                    ),
                    default=(
                        action_label_default
                    ),
                )
            )

        return (
            user_notification_service
            .safe_create(
                db,
                recipient_user_id=user_id,
                title=title,
                message=message,
                notification_type=(
                    notification_type
                ),
                priority=priority,
                source=source,
                event_type=event_type,
                action_url=action_url,
                action_label=action_label,
                entity_type=entity_type,
                entity_id=entity_id,
                image_url=image_url,
                metadata=metadata or {},
                is_global=False,
                requires_action=(
                    requires_action
                ),
                expires_at=expires_at,
            )
        )


localized_user_notification_service = (
    LocalizedUserNotificationService()
)