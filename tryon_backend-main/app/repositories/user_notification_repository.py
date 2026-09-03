from datetime import datetime

from sqlalchemy import (
    and_,
    func,
    or_,
    select,
)
from sqlalchemy.orm import Session

from app.models.user_notification import (
    UserNotification,
)
from app.models.user_notification_receipt import (
    UserNotificationReceipt,
)


class UserNotificationRepository:
    def _visibility_condition(
        self,
        *,
        user_id: int,
    ):
        return or_(
            UserNotification.recipient_user_id
            == user_id,
            and_(
                UserNotification.is_global.is_(True),
                UserNotification.recipient_user_id.is_(
                    None
                ),
            ),
        )

    def _active_condition(self):
        return and_(
            UserNotification.is_active.is_(True),
            or_(
                UserNotification.published_at.is_(
                    None
                ),
                UserNotification.published_at
                <= func.now(),
            ),
            or_(
                UserNotification.expires_at.is_(
                    None
                ),
                UserNotification.expires_at
                > func.now(),
            ),
        )

    def get_visible(
        self,
        db: Session,
        *,
        user_id: int,
        notification_id: int,
    ) -> UserNotification | None:
        statement = select(
            UserNotification
        ).where(
            UserNotification.id
            == notification_id,
            self._visibility_condition(
                user_id=user_id
            ),
            self._active_condition(),
        )

        return db.execute(
            statement
        ).scalar_one_or_none()

    def get_receipt(
        self,
        db: Session,
        *,
        user_id: int,
        notification_id: int,
    ) -> UserNotificationReceipt | None:
        statement = select(
            UserNotificationReceipt
        ).where(
            UserNotificationReceipt.user_id
            == user_id,
            UserNotificationReceipt.notification_id
            == notification_id,
        )

        return db.execute(
            statement
        ).scalar_one_or_none()

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
    ):
        statement = (
            select(
                UserNotification,
                UserNotificationReceipt,
            )
            .outerjoin(
                UserNotificationReceipt,
                and_(
                    UserNotificationReceipt.notification_id
                    == UserNotification.id,
                    UserNotificationReceipt.user_id
                    == user_id,
                ),
            )
            .where(
                self._visibility_condition(
                    user_id=user_id
                ),
                self._active_condition(),
            )
        )

        if notification_type:
            statement = statement.where(
                UserNotification.notification_type
                == notification_type
            )

        if priority:
            statement = statement.where(
                UserNotification.priority
                == priority
            )

        if source:
            statement = statement.where(
                UserNotification.source
                == source
            )

        if event_type:
            statement = statement.where(
                UserNotification.event_type
                == event_type
            )

        if requires_action is not None:
            statement = statement.where(
                UserNotification.requires_action.is_(
                    requires_action
                )
            )

        if is_read is not None:
            if is_read:
                statement = statement.where(
                    UserNotificationReceipt.is_read.is_(
                        True
                    )
                )
            else:
                statement = statement.where(
                    or_(
                        UserNotificationReceipt.id.is_(
                            None
                        ),
                        UserNotificationReceipt.is_read.is_(
                            False
                        ),
                    )
                )

        if is_archived is not None:
            if is_archived:
                statement = statement.where(
                    UserNotificationReceipt.is_archived.is_(
                        True
                    )
                )
            else:
                statement = statement.where(
                    or_(
                        UserNotificationReceipt.id.is_(
                            None
                        ),
                        UserNotificationReceipt.is_archived.is_(
                            False
                        ),
                    )
                )

        if search:
            pattern = f"%{search.strip()}%"

            statement = statement.where(
                or_(
                    UserNotification.title.ilike(
                        pattern
                    ),
                    UserNotification.message.ilike(
                        pattern
                    ),
                    UserNotification.event_type.ilike(
                        pattern
                    ),
                )
            )

        if created_from:
            statement = statement.where(
                UserNotification.created_at
                >= created_from
            )

        if created_to:
            statement = statement.where(
                UserNotification.created_at
                < created_to
            )

        statement = (
            statement
            .order_by(
                UserNotification.created_at.desc(),
                UserNotification.id.desc(),
            )
            .offset(skip)
            .limit(limit)
        )

        return db.execute(
            statement
        ).all()

    def count_for_user(
        self,
        db: Session,
        *,
        user_id: int,
        is_read: bool | None = None,
        is_archived: bool | None = False,
        priorities: list[str] | None = None,
        requires_action: bool | None = None,
    ) -> int:
        statement = (
            select(
                func.count(
                    UserNotification.id
                )
            )
            .outerjoin(
                UserNotificationReceipt,
                and_(
                    UserNotificationReceipt.notification_id
                    == UserNotification.id,
                    UserNotificationReceipt.user_id
                    == user_id,
                ),
            )
            .where(
                self._visibility_condition(
                    user_id=user_id
                ),
                self._active_condition(),
            )
        )

        if is_read is not None:
            if is_read:
                statement = statement.where(
                    UserNotificationReceipt.is_read.is_(
                        True
                    )
                )
            else:
                statement = statement.where(
                    or_(
                        UserNotificationReceipt.id.is_(
                            None
                        ),
                        UserNotificationReceipt.is_read.is_(
                            False
                        ),
                    )
                )

        if is_archived is not None:
            if is_archived:
                statement = statement.where(
                    UserNotificationReceipt.is_archived.is_(
                        True
                    )
                )
            else:
                statement = statement.where(
                    or_(
                        UserNotificationReceipt.id.is_(
                            None
                        ),
                        UserNotificationReceipt.is_archived.is_(
                            False
                        ),
                    )
                )

        if priorities:
            statement = statement.where(
                UserNotification.priority.in_(
                    priorities
                )
            )

        if requires_action is not None:
            statement = statement.where(
                UserNotification.requires_action.is_(
                    requires_action
                )
            )

        return int(
            db.execute(
                statement
            ).scalar_one()
        )


user_notification_repository = (
    UserNotificationRepository()
)