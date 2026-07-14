from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.token_purchase import TokenPurchase
from app.repositories.base import BaseRepository


class TokenPurchaseRepository(BaseRepository[TokenPurchase]):
    def __init__(self):
        super().__init__(TokenPurchase)

    def get_by_checkout_session_id(
        self,
        db: Session,
        checkout_session_id: str,
    ) -> TokenPurchase | None:
        statement = select(TokenPurchase).where(
            TokenPurchase.provider_checkout_session_id
            == checkout_session_id
        )

        return db.execute(statement).scalar_one_or_none()

    def get_by_payment_intent_id(
        self,
        db: Session,
        payment_intent_id: str,
    ) -> TokenPurchase | None:
        statement = select(TokenPurchase).where(
            TokenPurchase.provider_payment_intent_id
            == payment_intent_id
        )

        return db.execute(statement).scalar_one_or_none()

    def get_for_update(
        self,
        db: Session,
        purchase_id: int,
    ) -> TokenPurchase | None:
        statement = (
            select(TokenPurchase)
            .where(TokenPurchase.id == purchase_id)
            .with_for_update()
        )

        return db.execute(statement).scalar_one_or_none()

    def list_by_user_id(
        self,
        db: Session,
        *,
        user_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[TokenPurchase]:
        statement = (
            select(TokenPurchase)
            .where(TokenPurchase.user_id == user_id)
            .order_by(TokenPurchase.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())

    def count_by_user_id(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> int:
        statement = (
            select(func.count(TokenPurchase.id))
            .where(TokenPurchase.user_id == user_id)
        )

        return int(db.execute(statement).scalar_one())

    def list_all_filtered(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[TokenPurchase]:
        statement = select(TokenPurchase)

        if user_id is not None:
            statement = statement.where(
                TokenPurchase.user_id == user_id
            )

        if status is not None:
            statement = statement.where(
                TokenPurchase.status == status
            )

        statement = (
            statement
            .order_by(TokenPurchase.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())

    def count_filtered(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        status: str | None = None,
    ) -> int:
        statement = select(func.count(TokenPurchase.id))

        if user_id is not None:
            statement = statement.where(
                TokenPurchase.user_id == user_id
            )

        if status is not None:
            statement = statement.where(
                TokenPurchase.status == status
            )

        return int(db.execute(statement).scalar_one())


token_purchase_repository = TokenPurchaseRepository()