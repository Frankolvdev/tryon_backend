from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import UserStatus
from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self):
        super().__init__(User)

    def get_by_email(self, db: Session, email: str) -> User | None:
        statement = select(User).where(User.email == email)
        return db.execute(statement).scalar_one_or_none()

    def count_all(self, db: Session) -> int:
        statement = select(func.count()).select_from(User)
        return int(db.execute(statement).scalar_one())

    def count_active(self, db: Session) -> int:
        statement = (
            select(func.count())
            .select_from(User)
            .where(User.is_active.is_(True))
            .where(User.deleted_at.is_(None))
        )
        return int(db.execute(statement).scalar_one())

    def count_suspended(self, db: Session) -> int:
        statement = (
            select(func.count())
            .select_from(User)
            .where(User.status == UserStatus.SUSPENDED.value)
        )
        return int(db.execute(statement).scalar_one())

    def count_deleted(self, db: Session) -> int:
        statement = (
            select(func.count())
            .select_from(User)
            .where(User.deleted_at.is_not(None))
        )
        return int(db.execute(statement).scalar_one())

    def list_users(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 50,
        include_deleted: bool = False,
    ) -> list[User]:
        statement = select(User).order_by(User.created_at.desc())

        if not include_deleted:
            statement = statement.where(User.deleted_at.is_(None))

        statement = statement.offset(skip).limit(limit)

        return list(db.execute(statement).scalars().all())


user_repository = UserRepository()