from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.oauth_account import OAuthAccount
from app.repositories.base import BaseRepository


class OAuthAccountRepository(BaseRepository[OAuthAccount]):
    def __init__(self) -> None:
        super().__init__(OAuthAccount)

    def get_by_provider_identity(
        self,
        db: Session,
        *,
        provider: str,
        provider_user_id: str,
    ) -> OAuthAccount | None:
        statement = select(OAuthAccount).where(
            OAuthAccount.provider == provider,
            OAuthAccount.provider_user_id == provider_user_id,
        )
        return db.execute(statement).scalar_one_or_none()

    def get_by_user_provider(
        self,
        db: Session,
        *,
        user_id: int,
        provider: str,
    ) -> OAuthAccount | None:
        statement = select(OAuthAccount).where(
            OAuthAccount.user_id == user_id,
            OAuthAccount.provider == provider,
        )
        return db.execute(statement).scalar_one_or_none()


oauth_account_repository = OAuthAccountRepository()
