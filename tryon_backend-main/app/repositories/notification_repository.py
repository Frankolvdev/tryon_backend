from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    def __init__(self):
        super().__init__(Notification)

    def list_all(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Notification]:
        statement = (
            select(Notification)
            .order_by(Notification.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())

    def list_unread(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Notification]:
        statement = (
            select(Notification)
            .where(Notification.is_read.is_(False))
            .order_by(Notification.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())

    def count_unread(self, db: Session) -> int:
        statement = (
            select(func.count())
            .select_from(Notification)
            .where(Notification.is_read.is_(False))
        )

        return int(db.execute(statement).scalar_one())


notification_repository = NotificationRepository()