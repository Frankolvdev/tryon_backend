import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.common.exceptions import (
    NotFoundException,
)
from app.common.time import utc_now
from app.common.user_notification_enums import (
    UserNotificationPriority,
    UserNotificationSource,
    UserNotificationType,
)
from app.models.user_notification import (
    UserNotification,
)
from app.models.user_notification_receipt import (
    UserNotificationReceipt,
)
from app.observability.context import (
    get_correlation_id,
)
from app.repositories.user_notification_repository import (
    user_notification_repository,
)
from app.schemas.user_notification import (
    UserNotificationBulkResponse,
    UserNotificationCountResponse,
    UserNotificationCreate,
    UserNotificationListResponse,
    UserNotificationResponse,
)


logger = logging.getLogger(
    "app.user_notifications"
)


class UserNotificationService:
    VALID_TYPES = {
        item.value
        for item in UserNotificationType
    }

    VALID_PRIORITIES = {
        item.value
        for item in UserNotificationPriority
    }

    VALID_SOURCES = {
        item.value
        for item in UserNotificationSource
    }

    def _dump_json(
        self,
        value: dict[str, Any],
    ) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        )

    def _load_json(
        self,
        value: str | None,
    ) -> dict[str, Any]:
        if not value:
            return {}

        try:
            result = json.loads(value)

            if isinstance(result, dict):
                return result

        except (
            TypeError,
            json.JSONDecodeError,
        ):
            pass

        return {}

    def _normalize(
        self,
        value: str,
        *,
        allowed: set[str],
        field_name: str,
    ) -> str:
        normalized = value.strip().lower()

        if normalized not in allowed:
            raise ValueError(
                f"Invalid {field_name}."
            )

        return normalized

    def _get_or_create_receipt(
        self,
        db: Session,
        *,
        user_id: int,
        notification_id: int,
    ) -> UserNotificationReceipt:
        receipt = (
            user_notification_repository
            .get_receipt(
                db,
                user_id=user_id,
                notification_id=(
                    notification_id
                ),
            )
        )

        if receipt is not None:
            return receipt

        receipt = UserNotificationReceipt(
            notification_id=(
                notification_id
            ),
            user_id=user_id,
        )

        db.add(receipt)
        db.flush()

        return receipt

    def _response(
        self,
        notification: UserNotification,
        receipt: UserNotificationReceipt | None,
    ) -> UserNotificationResponse:
        return UserNotificationResponse(
            id=notification.id,
            notification_type=(
                notification.notification_type
            ),
            priority=notification.priority,
            source=notification.source,
            event_type=notification.event_type,
            title=notification.title,
            message=notification.message,
            action_url=notification.action_url,
            action_label=(
                notification.action_label
            ),
            image_url=notification.image_url,
            entity_type=notification.entity_type,
            entity_id=notification.entity_id,
            metadata=self._load_json(
                notification.metadata_json
            ),
            is_global=notification.is_global,
            requires_action=(
                notification.requires_action
            ),
            is_read=(
                receipt.is_read
                if receipt is not None
                else False
            ),
            is_archived=(
                receipt.is_archived
                if receipt is not None
                else False
            ),
            read_at=(
                receipt.read_at
                if receipt is not None
                else None
            ),
            archived_at=(
                receipt.archived_at
                if receipt is not None
                else None
            ),
            published_at=(
                notification.published_at
            ),
            expires_at=notification.expires_at,
            created_at=notification.created_at,
        )

    def create(
        self,
        db: Session,
        *,
        data: UserNotificationCreate,
        commit: bool = True,
    ) -> UserNotification:
        if (
            data.recipient_user_id is None
            and not data.is_global
        ):
            raise ValueError(
                "A user notification requires "
                "recipient_user_id or "
                "is_global=true."
            )

        notification = UserNotification(
            recipient_user_id=(
                data.recipient_user_id
            ),
            notification_type=self._normalize(
                data.notification_type,
                allowed=self.VALID_TYPES,
                field_name=(
                    "notification type"
                ),
            ),
            priority=self._normalize(
                data.priority,
                allowed=self.VALID_PRIORITIES,
                field_name=(
                    "notification priority"
                ),
            ),
            source=self._normalize(
                data.source,
                allowed=self.VALID_SOURCES,
                field_name=(
                    "notification source"
                ),
            ),
            event_type=data.event_type,
            title=data.title,
            message=data.message,
            action_url=data.action_url,
            action_label=data.action_label,
            entity_type=data.entity_type,
            entity_id=(
                str(data.entity_id)
                if data.entity_id
                is not None
                else None
            ),
            image_url=data.image_url,
            correlation_id=(
                get_correlation_id()
            ),
            metadata_json=self._dump_json(
                data.metadata
            ),
            is_global=data.is_global,
            requires_action=(
                data.requires_action
            ),
            published_at=(
                data.published_at
                or utc_now()
            ),
            expires_at=data.expires_at,
        )

        db.add(notification)

        if commit:
            db.commit()
            db.refresh(notification)
        else:
            db.flush()

        logger.info(
            "User notification created.",
            extra={
                "notification_id": (
                    notification.id
                ),
                "recipient_user_id": (
                    notification
                    .recipient_user_id
                ),
                "event_type": (
                    notification.event_type
                ),
                "source": (
                    notification.source
                ),
                "is_global": (
                    notification.is_global
                ),
            },
        )

        if (
            commit
            and notification
            .recipient_user_id
            is not None
        ):
            try:
                from app.services.user_notification_delivery_service import (
                    user_notification_delivery_service,
                )

                (
                    user_notification_delivery_service
                    .deliver(
                        db,
                        notification=(
                            notification
                        ),
                    )
                )

            except Exception:
                logger.exception(
                    "User notification "
                    "external delivery failed.",
                    extra={
                        "notification_id": (
                            notification.id
                        ),
                        "recipient_user_id": (
                            notification
                            .recipient_user_id
                        ),
                    },
                )

        return notification

    def safe_create(
        self,
        db: Session,
        *,
        recipient_user_id: int | None,
        title: str,
        message: str,
        notification_type: str = "info",
        priority: str = "normal",
        source: str = "system",
        event_type: str | None = None,
        action_url: str | None = None,
        action_label: str | None = None,
        entity_type: str | None = None,
        entity_id: str | int | None = None,
        image_url: str | None = None,
        metadata: dict[str, Any] | None = None,
        is_global: bool = False,
        requires_action: bool = False,
        expires_at: datetime | None = None,
    ) -> UserNotification | None:
        try:
            return self.create(
                db,
                data=UserNotificationCreate(
                    recipient_user_id=(
                        recipient_user_id
                    ),
                    notification_type=(
                        notification_type
                    ),
                    priority=priority,
                    source=source,
                    event_type=event_type,
                    title=title,
                    message=message,
                    action_url=action_url,
                    action_label=(
                        action_label
                    ),
                    entity_type=entity_type,
                    entity_id=entity_id,
                    image_url=image_url,
                    metadata=metadata or {},
                    is_global=is_global,
                    requires_action=(
                        requires_action
                    ),
                    expires_at=expires_at,
                ),
            )

        except Exception:
            db.rollback()

            logger.exception(
                "Could not create user "
                "notification.",
                extra={
                    "recipient_user_id": (
                        recipient_user_id
                    ),
                    "event_type": (
                        event_type
                    ),
                    "source": source,
                },
            )

            return None

    def list_for_user(
        self,
        db: Session,
        *,
        user_id: int,
        notification_type: str | None = None,
        priority: str | None = None,
        source: str | None = None,
        event_type: str | None = None,
        is_read: bool | None = None,
        is_archived: bool | None = False,
        requires_action: bool | None = None,
        search: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> UserNotificationListResponse:
        rows = (
            user_notification_repository
            .list_for_user(
                db,
                user_id=user_id,
                notification_type=(
                    notification_type
                ),
                priority=priority,
                source=source,
                event_type=event_type,
                is_read=is_read,
                is_archived=is_archived,
                requires_action=(
                    requires_action
                ),
                search=search,
                created_from=created_from,
                created_to=created_to,
                skip=skip,
                limit=limit,
            )
        )

        items = [
            self._response(
                notification,
                receipt,
            )
            for notification, receipt
            in rows
        ]

        total = (
            user_notification_repository
            .count_for_user(
                db,
                user_id=user_id,
                is_archived=(
                    is_archived
                ),
            )
        )

        unread = (
            user_notification_repository
            .count_for_user(
                db,
                user_id=user_id,
                is_read=False,
                is_archived=False,
            )
        )

        return UserNotificationListResponse(
            items=items,
            total=total,
            unread=unread,
            skip=skip,
            limit=limit,
        )

    def get_for_user(
        self,
        db: Session,
        *,
        user_id: int,
        notification_id: int,
    ) -> UserNotificationResponse:
        notification = (
            user_notification_repository
            .get_visible(
                db,
                user_id=user_id,
                notification_id=(
                    notification_id
                ),
            )
        )

        if notification is None:
            raise NotFoundException(
                "Notification not found."
            )

        receipt = (
            user_notification_repository
            .get_receipt(
                db,
                user_id=user_id,
                notification_id=(
                    notification_id
                ),
            )
        )

        return self._response(
            notification,
            receipt,
        )

    def counts(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> UserNotificationCountResponse:
        return (
            UserNotificationCountResponse(
                total=(
                    user_notification_repository
                    .count_for_user(
                        db,
                        user_id=user_id,
                        is_archived=False,
                    )
                ),
                unread=(
                    user_notification_repository
                    .count_for_user(
                        db,
                        user_id=user_id,
                        is_read=False,
                        is_archived=False,
                    )
                ),
                high_priority=(
                    user_notification_repository
                    .count_for_user(
                        db,
                        user_id=user_id,
                        is_archived=False,
                        priorities=[
                            "high",
                            "urgent",
                        ],
                    )
                ),
                requires_action=(
                    user_notification_repository
                    .count_for_user(
                        db,
                        user_id=user_id,
                        is_archived=False,
                        requires_action=True,
                    )
                ),
            )
        )

    def mark_read(
        self,
        db: Session,
        *,
        user_id: int,
        notification_id: int,
    ) -> UserNotificationResponse:
        notification = (
            user_notification_repository
            .get_visible(
                db,
                user_id=user_id,
                notification_id=(
                    notification_id
                ),
            )
        )

        if notification is None:
            raise NotFoundException(
                "Notification not found."
            )

        receipt = (
            self._get_or_create_receipt(
                db,
                user_id=user_id,
                notification_id=(
                    notification_id
                ),
            )
        )

        receipt.is_read = True
        receipt.read_at = utc_now()

        db.add(receipt)
        db.commit()
        db.refresh(receipt)

        return self._response(
            notification,
            receipt,
        )

    def mark_unread(
        self,
        db: Session,
        *,
        user_id: int,
        notification_id: int,
    ) -> UserNotificationResponse:
        notification = (
            user_notification_repository
            .get_visible(
                db,
                user_id=user_id,
                notification_id=(
                    notification_id
                ),
            )
        )

        if notification is None:
            raise NotFoundException(
                "Notification not found."
            )

        receipt = (
            self._get_or_create_receipt(
                db,
                user_id=user_id,
                notification_id=(
                    notification_id
                ),
            )
        )

        receipt.is_read = False
        receipt.read_at = None

        db.add(receipt)
        db.commit()
        db.refresh(receipt)

        return self._response(
            notification,
            receipt,
        )

    def archive(
        self,
        db: Session,
        *,
        user_id: int,
        notification_id: int,
    ) -> UserNotificationResponse:
        notification = (
            user_notification_repository
            .get_visible(
                db,
                user_id=user_id,
                notification_id=(
                    notification_id
                ),
            )
        )

        if notification is None:
            raise NotFoundException(
                "Notification not found."
            )

        receipt = (
            self._get_or_create_receipt(
                db,
                user_id=user_id,
                notification_id=(
                    notification_id
                ),
            )
        )

        receipt.is_archived = True
        receipt.archived_at = utc_now()

        db.add(receipt)
        db.commit()
        db.refresh(receipt)

        return self._response(
            notification,
            receipt,
        )

    def mark_many_read(
        self,
        db: Session,
        *,
        user_id: int,
        notification_ids: list[int],
    ) -> UserNotificationBulkResponse:
        affected = 0

        for notification_id in set(
            notification_ids
        ):
            notification = (
                user_notification_repository
                .get_visible(
                    db,
                    user_id=user_id,
                    notification_id=(
                        notification_id
                    ),
                )
            )

            if notification is None:
                continue

            receipt = (
                self._get_or_create_receipt(
                    db,
                    user_id=user_id,
                    notification_id=(
                        notification_id
                    ),
                )
            )

            if not receipt.is_read:
                receipt.is_read = True
                receipt.read_at = utc_now()

                db.add(receipt)
                affected += 1

        db.commit()

        return UserNotificationBulkResponse(
            success=True,
            affected=affected,
        )

    def mark_all_read(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> UserNotificationBulkResponse:
        rows = (
            user_notification_repository
            .list_for_user(
                db,
                user_id=user_id,
                is_read=False,
                is_archived=False,
                skip=0,
                limit=10000,
            )
        )

        affected = 0
        now = utc_now()

        for notification, receipt in rows:
            if receipt is None:
                receipt = (
                    UserNotificationReceipt(
                        notification_id=(
                            notification.id
                        ),
                        user_id=user_id,
                    )
                )

            receipt.is_read = True
            receipt.read_at = now

            db.add(receipt)
            affected += 1

        db.commit()

        return UserNotificationBulkResponse(
            success=True,
            affected=affected,
        )


user_notification_service = (
    UserNotificationService()
)