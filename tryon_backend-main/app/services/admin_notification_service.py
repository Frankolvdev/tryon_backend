import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import (
    func,
    select,
    update,
)
from sqlalchemy.orm import Session

from app.common.exceptions import (
    NotFoundException,
)
from app.common.notification_enums import (
    AdminNotificationPriority,
    AdminNotificationSource,
    AdminNotificationType,
)
from app.common.time import utc_now
from app.models.admin_notification import (
    AdminNotification,
)
from app.models.user import User
from app.observability.context import (
    get_correlation_id,
)
from app.repositories.admin_notification_repository import (
    admin_notification_repository,
)
from app.schemas.admin_notification import (
    AdminNotificationBulkActionResponse,
    AdminNotificationCountResponse,
    AdminNotificationCreate,
    AdminNotificationListResponse,
    AdminNotificationResponse,
)


logger = logging.getLogger(
    "app.admin_notifications"
)


class AdminNotificationService:
    VALID_TYPES = {
        item.value
        for item in AdminNotificationType
    }

    VALID_PRIORITIES = {
        item.value
        for item in AdminNotificationPriority
    }

    VALID_SOURCES = {
        item.value
        for item in AdminNotificationSource
    }

    def _serialize_metadata(
        self,
        metadata: dict[str, Any],
    ) -> str:
        return json.dumps(
            metadata,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        )

    def _parse_metadata(
        self,
        value: str | None,
    ) -> dict[str, Any]:
        if not value:
            return {}

        try:
            parsed = json.loads(value)

            if isinstance(parsed, dict):
                return parsed

        except (
            TypeError,
            json.JSONDecodeError,
        ):
            pass

        return {}

    def _response(
        self,
        notification: AdminNotification,
    ) -> AdminNotificationResponse:
        return AdminNotificationResponse(
            id=notification.id,
            recipient_user_id=(
                notification.recipient_user_id
            ),
            notification_type=(
                notification.notification_type
            ),
            priority=notification.priority,
            source=notification.source,
            event_type=notification.event_type,
            title=notification.title,
            message=notification.message,
            action_url=notification.action_url,
            action_label=notification.action_label,
            entity_type=notification.entity_type,
            entity_id=notification.entity_id,
            correlation_id=(
                notification.correlation_id
            ),
            metadata=self._parse_metadata(
                notification.metadata_json
            ),
            is_global=notification.is_global,
            is_read=notification.is_read,
            is_archived=(
                notification.is_archived
            ),
            requires_action=(
                notification.requires_action
            ),
            read_at=notification.read_at,
            archived_at=notification.archived_at,
            expires_at=notification.expires_at,
            created_at=notification.created_at,
            updated_at=notification.updated_at,
        )

    def _normalize_type(
        self,
        value: str,
    ) -> str:
        normalized = (
            value.strip().lower()
        )

        if normalized not in self.VALID_TYPES:
            raise ValueError(
                "Invalid notification type."
            )

        return normalized

    def _normalize_priority(
        self,
        value: str,
    ) -> str:
        normalized = (
            value.strip().lower()
        )

        if normalized not in self.VALID_PRIORITIES:
            raise ValueError(
                "Invalid notification priority."
            )

        return normalized

    def _normalize_source(
        self,
        value: str,
    ) -> str:
        normalized = (
            value.strip().lower()
        )

        if normalized not in self.VALID_SOURCES:
            return normalized

        return normalized

    def create(
        self,
        db: Session,
        *,
        data: AdminNotificationCreate,
        commit: bool = True,
    ) -> AdminNotificationResponse:
        notification_type = (
            self._normalize_type(
                data.notification_type
            )
        )

        priority = self._normalize_priority(
            data.priority
        )

        source = self._normalize_source(
            data.source
        )

        if (
            data.recipient_user_id is None
            and not data.is_global
        ):
            raise ValueError(
                "A notification requires either "
                "recipient_user_id or is_global=true."
            )

        notification = AdminNotification(
            recipient_user_id=(
                data.recipient_user_id
            ),
            notification_type=(
                notification_type
            ),
            priority=priority,
            source=source,
            event_type=data.event_type,
            title=data.title,
            message=data.message,
            action_url=data.action_url,
            action_label=data.action_label,
            entity_type=data.entity_type,
            entity_id=(
                str(data.entity_id)
                if data.entity_id is not None
                else None
            ),
            correlation_id=(
                data.correlation_id
                or get_correlation_id()
            ),
            metadata_json=(
                self._serialize_metadata(
                    data.metadata
                )
            ),
            is_global=data.is_global,
            requires_action=(
                data.requires_action
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
            "Admin notification created.",
            extra={
                "notification_id": (
                    notification.id
                ),
                "recipient_user_id": (
                    notification
                    .recipient_user_id
                ),
                "notification_type": (
                    notification
                    .notification_type
                ),
                "priority": (
                    notification.priority
                ),
                "source": (
                    notification.source
                ),
                "event_type": (
                    notification.event_type
                ),
                "is_global": (
                    notification.is_global
                ),
            },
        )

        return self._response(
            notification
        )

    def safe_create(
        self,
        db: Session,
        *,
        title: str,
        message: str,
        notification_type: str = "info",
        priority: str = "normal",
        source: str = "system",
        recipient_user_id: int | None = None,
        is_global: bool = True,
        event_type: str | None = None,
        entity_type: str | None = None,
        entity_id: str | int | None = None,
        action_url: str | None = None,
        action_label: str | None = None,
        requires_action: bool = False,
        metadata: dict[str, Any] | None = None,
        expires_at: datetime | None = None,
    ) -> AdminNotificationResponse | None:
        try:
            return self.create(
                db,
                data=AdminNotificationCreate(
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
                    action_label=action_label,
                    entity_type=entity_type,
                    entity_id=entity_id,
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
                "Could not create admin notification.",
                extra={
                    "title": title,
                    "source": source,
                    "event_type": event_type,
                },
            )

            return None

    def get_for_user(
        self,
        db: Session,
        *,
        notification_id: int,
        user_id: int,
    ) -> AdminNotification:
        notification = (
            admin_notification_repository
            .get_visible_by_id(
                db,
                notification_id=(
                    notification_id
                ),
                recipient_user_id=user_id,
            )
        )

        if notification is None:
            raise NotFoundException(
                "Notification not found."
            )

        return notification

    def get_response_for_user(
        self,
        db: Session,
        *,
        notification_id: int,
        user_id: int,
    ) -> AdminNotificationResponse:
        notification = self.get_for_user(
            db,
            notification_id=(
                notification_id
            ),
            user_id=user_id,
        )

        return self._response(
            notification
        )

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
        entity_type: str | None = None,
        entity_id: str | None = None,
        search: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        include_expired: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> AdminNotificationListResponse:
        items = (
            admin_notification_repository
            .list_for_user(
                db,
                recipient_user_id=user_id,
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
                entity_type=entity_type,
                entity_id=entity_id,
                search=search,
                created_from=created_from,
                created_to=created_to,
                include_expired=(
                    include_expired
                ),
                skip=skip,
                limit=limit,
            )
        )

        total = (
            admin_notification_repository
            .count_for_user(
                db,
                recipient_user_id=user_id,
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
                entity_type=entity_type,
                entity_id=entity_id,
                search=search,
                created_from=created_from,
                created_to=created_to,
                include_expired=(
                    include_expired
                ),
            )
        )

        unread = (
            admin_notification_repository
            .count_for_user(
                db,
                recipient_user_id=user_id,
                is_read=False,
                is_archived=False,
                include_expired=False,
            )
        )

        return AdminNotificationListResponse(
            items=[
                self._response(item)
                for item in items
            ],
            total=total,
            unread=unread,
            skip=skip,
            limit=limit,
        )

    def counts(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> AdminNotificationCountResponse:
        total = (
            admin_notification_repository
            .count_for_user(
                db,
                recipient_user_id=user_id,
                is_archived=False,
                include_expired=False,
            )
        )

        unread = (
            admin_notification_repository
            .count_for_user(
                db,
                recipient_user_id=user_id,
                is_read=False,
                is_archived=False,
                include_expired=False,
            )
        )

        urgent = (
            admin_notification_repository
            .count_for_user(
                db,
                recipient_user_id=user_id,
                priority="urgent",
                is_archived=False,
                include_expired=False,
            )
        )

        requires_action = (
            admin_notification_repository
            .count_for_user(
                db,
                recipient_user_id=user_id,
                requires_action=True,
                is_archived=False,
                include_expired=False,
            )
        )

        return AdminNotificationCountResponse(
            total=total,
            unread=unread,
            urgent=urgent,
            requires_action=(
                requires_action
            ),
        )

    def mark_read(
        self,
        db: Session,
        *,
        notification_id: int,
        user_id: int,
    ) -> AdminNotificationResponse:
        notification = self.get_for_user(
            db,
            notification_id=(
                notification_id
            ),
            user_id=user_id,
        )

        if not notification.is_read:
            notification.is_read = True
            notification.read_at = utc_now()

            db.add(notification)
            db.commit()
            db.refresh(notification)

        return self._response(
            notification
        )

    def mark_unread(
        self,
        db: Session,
        *,
        notification_id: int,
        user_id: int,
    ) -> AdminNotificationResponse:
        notification = self.get_for_user(
            db,
            notification_id=(
                notification_id
            ),
            user_id=user_id,
        )

        notification.is_read = False
        notification.read_at = None

        db.add(notification)
        db.commit()
        db.refresh(notification)

        return self._response(
            notification
        )

    def mark_many_read(
        self,
        db: Session,
        *,
        notification_ids: list[int],
        user_id: int,
    ) -> AdminNotificationBulkActionResponse:
        affected = 0

        for notification_id in set(
            notification_ids
        ):
            notification = (
                admin_notification_repository
                .get_visible_by_id(
                    db,
                    notification_id=(
                        notification_id
                    ),
                    recipient_user_id=user_id,
                )
            )

            if (
                notification is not None
                and not notification.is_read
            ):
                notification.is_read = True
                notification.read_at = utc_now()
                db.add(notification)
                affected += 1

        db.commit()

        return AdminNotificationBulkActionResponse(
            success=True,
            affected=affected,
        )

    def mark_all_read(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> AdminNotificationBulkActionResponse:
        notifications = (
            admin_notification_repository
            .list_for_user(
                db,
                recipient_user_id=user_id,
                is_read=False,
                is_archived=False,
                include_expired=False,
                skip=0,
                limit=10000,
            )
        )

        now = utc_now()

        for notification in notifications:
            notification.is_read = True
            notification.read_at = now
            db.add(notification)

        db.commit()

        return AdminNotificationBulkActionResponse(
            success=True,
            affected=len(notifications),
        )

    def archive(
        self,
        db: Session,
        *,
        notification_id: int,
        user_id: int,
    ) -> AdminNotificationResponse:
        notification = self.get_for_user(
            db,
            notification_id=(
                notification_id
            ),
            user_id=user_id,
        )

        notification.is_archived = True
        notification.archived_at = utc_now()

        db.add(notification)
        db.commit()
        db.refresh(notification)

        return self._response(
            notification
        )

    def archive_many(
        self,
        db: Session,
        *,
        notification_ids: list[int],
        user_id: int,
    ) -> AdminNotificationBulkActionResponse:
        affected = 0
        now = utc_now()

        for notification_id in set(
            notification_ids
        ):
            notification = (
                admin_notification_repository
                .get_visible_by_id(
                    db,
                    notification_id=(
                        notification_id
                    ),
                    recipient_user_id=user_id,
                )
            )

            if (
                notification is not None
                and not notification.is_archived
            ):
                notification.is_archived = True
                notification.archived_at = now
                db.add(notification)
                affected += 1

        db.commit()

        return AdminNotificationBulkActionResponse(
            success=True,
            affected=affected,
        )


admin_notification_service = (
    AdminNotificationService()
)