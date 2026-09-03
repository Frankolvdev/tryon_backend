from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.refresh_token import RefreshToken
from app.repositories.base import BaseRepository


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    def __init__(self):
        super().__init__(RefreshToken)

    def get_by_token_hash(
        self,
        db: Session,
        token_hash: str,
    ) -> RefreshToken | None:
        statement = select(RefreshToken).where(
            RefreshToken.token_hash == token_hash
        )
        return db.execute(statement).scalar_one_or_none()

    def get_active_by_user_id(
        self,
        db: Session,
        user_id: int,
    ) -> list[RefreshToken]:
        statement = (
            select(RefreshToken)
            .where(RefreshToken.user_id == user_id)
            .where(RefreshToken.is_revoked.is_(False))
            .order_by(RefreshToken.created_at.desc())
        )

        return list(db.execute(statement).scalars().all())

    def get_all_by_user_id(
        self,
        db: Session,
        user_id: int,
    ) -> list[RefreshToken]:
        statement = (
            select(RefreshToken)
            .where(RefreshToken.user_id == user_id)
            .order_by(RefreshToken.created_at.desc())
        )

        return list(db.execute(statement).scalars().all())


refresh_token_repository = RefreshTokenRepository()