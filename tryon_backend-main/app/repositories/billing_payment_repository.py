from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.billing_payment import BillingPayment
from app.repositories.base import BaseRepository


class BillingPaymentRepository(BaseRepository[BillingPayment]):
    def __init__(self):
        super().__init__(BillingPayment)

    def get_by_checkout_session_id(
        self,
        db: Session,
        checkout_session_id: str,
    ) -> BillingPayment | None:
        statement = select(BillingPayment).where(
            BillingPayment.provider_checkout_session_id
            == checkout_session_id
        )

        return db.execute(statement).scalar_one_or_none()

    def get_by_payment_intent_id(
        self,
        db: Session,
        payment_intent_id: str,
    ) -> BillingPayment | None:
        statement = select(BillingPayment).where(
            BillingPayment.provider_payment_intent_id
            == payment_intent_id
        )

        return db.execute(statement).scalar_one_or_none()

    def get_for_update(
        self,
        db: Session,
        payment_id: int,
    ) -> BillingPayment | None:
        statement = (
            select(BillingPayment)
            .where(BillingPayment.id == payment_id)
            .with_for_update()
        )

        return db.execute(statement).scalar_one_or_none()

    def list_all_filtered(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        status: str | None = None,
        payment_type: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[BillingPayment]:
        statement = select(BillingPayment)

        if user_id is not None:
            statement = statement.where(
                BillingPayment.user_id == user_id
            )

        if status is not None:
            statement = statement.where(
                BillingPayment.status == status
            )

        if payment_type is not None:
            statement = statement.where(
                BillingPayment.payment_type == payment_type
            )

        statement = (
            statement
            .order_by(
                BillingPayment.created_at.desc(),
                BillingPayment.id.desc(),
            )
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
        payment_type: str | None = None,
    ) -> int:
        statement = select(func.count(BillingPayment.id))

        if user_id is not None:
            statement = statement.where(
                BillingPayment.user_id == user_id
            )

        if status is not None:
            statement = statement.where(
                BillingPayment.status == status
            )

        if payment_type is not None:
            statement = statement.where(
                BillingPayment.payment_type == payment_type
            )

        return int(db.execute(statement).scalar_one())


billing_payment_repository = BillingPaymentRepository()