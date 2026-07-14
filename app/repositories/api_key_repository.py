from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.api_key import ApiKey
from app.repositories.base import BaseRepository


class ApiKeyRepository(BaseRepository[ApiKey]):
    def __init__(self):
        super().__init__(ApiKey)

    def get_by_prefix(self, db: Session, key_prefix: str) -> ApiKey | None:
        statement = select(ApiKey).where(ApiKey.key_prefix == key_prefix)
        return db.execute(statement).scalar_one_or_none()

    def list_all(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ApiKey]:
        statement = (
            select(ApiKey)
            .order_by(ApiKey.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())

    def list_by_user_id(
        self,
        db: Session,
        user_id: int,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ApiKey]:
        statement = (
            select(ApiKey)
            .where(ApiKey.user_id == user_id)
            .order_by(ApiKey.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())


api_key_repository = ApiKeyRepository()