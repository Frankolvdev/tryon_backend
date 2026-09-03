from sqlalchemy.orm import Session

from app.common.enums import NotificationCategory, NotificationType
from app.common.exceptions import NotFoundException
from app.common.time import utc_now
from app.models.notification import Notification
from app.repositories.notification_repository import notification_repository
from app.schemas.notification import NotificationCreate


class NotificationService:
    def create_notification(
        self,
        db: Session,
        data: NotificationCreate,
    ) -> Notification:
        return notification_repository.create(
            db,
            data=data.model_dump(),
        )

    def info(
        self,
        db: Session,
        *,
        title: str,
        message: str,
        category: NotificationCategory = NotificationCategory.SYSTEM,
        metadata_json: str | None = None,
    ) -> Notification:
        return self.create_notification(
            db,
            NotificationCreate(
                notification_type=NotificationType.INFO,
                category=category,
                title=title,
                message=message,
                metadata_json=metadata_json,
            ),
        )

    def success(
        self,
        db: Session,
        *,
        title: str,
        message: str,
        category: NotificationCategory = NotificationCategory.SYSTEM,
        metadata_json: str | None = None,
    ) -> Notification:
        return self.create_notification(
            db,
            NotificationCreate(
                notification_type=NotificationType.SUCCESS,
                category=category,
                title=title,
                message=message,
                metadata_json=metadata_json,
            ),
        )

    def warning(
        self,
        db: Session,
        *,
        title: str,
        message: str,
        category: NotificationCategory = NotificationCategory.SYSTEM,
        metadata_json: str | None = None,
    ) -> Notification:
        return self.create_notification(
            db,
            NotificationCreate(
                notification_type=NotificationType.WARNING,
                category=category,
                title=title,
                message=message,
                metadata_json=metadata_json,
            ),
        )

    def error(
        self,
        db: Session,
        *,
        title: str,
        message: str,
        category: NotificationCategory = NotificationCategory.SYSTEM,
        metadata_json: str | None = None,
    ) -> Notification:
        return self.create_notification(
            db,
            NotificationCreate(
                notification_type=NotificationType.ERROR,
                category=category,
                title=title,
                message=message,
                metadata_json=metadata_json,
            ),
        )

    def list_notifications(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Notification]:
        return notification_repository.list_all(
            db,
            skip=skip,
            limit=limit,
        )

    def list_unread(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Notification]:
        return notification_repository.list_unread(
            db,
            skip=skip,
            limit=limit,
        )

    def count_unread(self, db: Session) -> int:
        return notification_repository.count_unread(db)

    def mark_as_read(
        self,
        db: Session,
        notification_id: int,
    ) -> Notification:
        notification = notification_repository.get_by_id(db, notification_id)

        if not notification:
            raise NotFoundException("Notification not found.")

        notification.is_read = True
        notification.read_at = utc_now()

        db.add(notification)
        db.commit()
        db.refresh(notification)

        return notification

    def mark_all_as_read(self, db: Session) -> None:
        notifications = notification_repository.list_unread(db, skip=0, limit=10000)

        for notification in notifications:
            notification.is_read = True
            notification.read_at = utc_now()
            db.add(notification)

        db.commit()

    def delete_notification(
        self,
        db: Session,
        notification_id: int,
    ) -> None:
        notification = notification_repository.get_by_id(db, notification_id)

        if not notification:
            return

        db.delete(notification)
        db.commit()

    def clear_all(self, db: Session) -> None:
        notifications = notification_repository.list_all(db, skip=0, limit=10000)

        for notification in notifications:
            db.delete(notification)

        db.commit()


notification_service = NotificationService()