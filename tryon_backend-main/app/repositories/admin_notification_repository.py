from datetime import datetime

from sqlalchemy import (
    and_,
    func,
    or_,
    select,
)
from sqlalchemy.orm import Session

from app.models.admin_notification import (
    AdminNotification,
)
from app.repositories.base import BaseRepository


class AdminNotificationRepository(
    BaseRepository[AdminNotification]
):
    def __init__(self):
        super().__init__(
            AdminNotification
        )

    def _visibility_condition(
        self,
        *,
        recipient_user_id: int,
    ):
        return or_(
            AdminNotification.recipient_user_id
            == recipient_user_id,
            and_(
                AdminNotification.is_global.is_(
                    True
                ),
                AdminNotification.recipient_user_id.is_(
                    None
                ),
            ),
        )

    def _apply_filters(
        self,
        statement,
        *,
        recipient_user_id: int,
        notification_type: str | None,
        priority: str | None,
        source: str | None,
        event_type: str | None,
        is_read: bool | None,
        is_archived: bool | None,
        requires_action: bool | None,
        entity_type: str | None,
        entity_id: str | None,
        search: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        include_expired: bool,
    ):
        statement = statement.where(
            self._visibility_condition(
                recipient_user_id=(
                    recipient_user_id
                )
            )
        )

        if notification_type:
            statement = statement.where(
                AdminNotification.notification_type
                == notification_type
            )

        if priority:
            statement = statement.where(
                AdminNotification.priority
                == priority
            )

        if source:
            statement = statement.where(
                AdminNotification.source
                == source
            )

        if event_type:
            statement = statement.where(
                AdminNotification.event_type
                == event_type
            )

        if is_read is not None:
            statement = statement.where(
                AdminNotification.is_read.is_(
                    is_read
                )
            )

        if is_archived is not None:
            statement = statement.where(
                AdminNotification.is_archived.is_(
                    is_archived
                )
            )

        if requires_action is not None:
            statement = statement.where(
                AdminNotification.requires_action.is_(
                    requires_action
                )
            )

        if entity_type:
            statement = statement.where(
                AdminNotification.entity_type
                == entity_type
            )

        if entity_id:
            statement = statement.where(
                AdminNotification.entity_id
                == entity_id
            )

        if search:
            pattern = (
                f"%{search.strip()}%"
            )

            statement = statement.where(
                or_(
                    AdminNotification.title.ilike(
                        pattern
                    ),
                    AdminNotification.message.ilike(
                        pattern
                    ),
                    AdminNotification.event_type.ilike(
                        pattern
                    ),
                    AdminNotification.entity_type.ilike(
                        pattern
                    ),
                    AdminNotification.entity_id.ilike(
                        pattern
                    ),
                )
            )

        if created_from:
            statement = statement.where(
                AdminNotification.created_at
                >= created_from
            )

        if created_to:
            statement = statement.where(
                AdminNotification.created_at
                < created_to
            )

        if not include_expired:
            statement = statement.where(
                or_(
                    AdminNotification.expires_at.is_(
                        None
                    ),
                    AdminNotification.expires_at
                    > func.now(),
                )
            )

        return statement

    def list_for_user(
        self,
        db: Session,
        *,
        recipient_user_id: int,
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
    ) -> list[AdminNotification]:
        statement = select(
            AdminNotification
        )

        statement = self._apply_filters(
            statement,
            recipient_user_id=(
                recipient_user_id
            ),
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

        statement = (
            statement
            .order_by(
                AdminNotification.created_at.desc(),
                AdminNotification.id.desc(),
            )
            .offset(skip)
            .limit(limit)
        )

        return list(
            db.execute(
                statement
            ).scalars().all()
        )

    def count_for_user(
        self,
        db: Session,
        *,
        recipient_user_id: int,
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
    ) -> int:
        statement = select(
            func.count(
                AdminNotification.id
            )
        )

        statement = self._apply_filters(
            statement,
            recipient_user_id=(
                recipient_user_id
            ),
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

        return int(
            db.execute(
                statement
            ).scalar_one()
        )

    def get_visible_by_id(
        self,
        db: Session,
        *,
        notification_id: int,
        recipient_user_id: int,
    ) -> AdminNotification | None:
        statement = (
            select(AdminNotification)
            .where(
                AdminNotification.id
                == notification_id,
                self._visibility_condition(
                    recipient_user_id=(
                        recipient_user_id
                    )
                ),
            )
        )

        return db.execute(
            statement
        ).scalar_one_or_none()


admin_notification_repository = (
    AdminNotificationRepository()
)