from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.billing_invoice import BillingInvoice
from app.repositories.base import BaseRepository


class BillingInvoiceRepository(BaseRepository[BillingInvoice]):
    def __init__(self):
        super().__init__(BillingInvoice)

    def get_by_provider_invoice_id(
        self,
        db: Session,
        provider_invoice_id: str,
    ) -> BillingInvoice | None:
        statement = select(BillingInvoice).where(
            BillingInvoice.provider_invoice_id
            == provider_invoice_id
        )

        return db.execute(statement).scalar_one_or_none()

    def list_all_filtered(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[BillingInvoice]:
        statement = select(BillingInvoice)

        if user_id is not None:
            statement = statement.where(
                BillingInvoice.user_id == user_id
            )

        if status is not None:
            statement = statement.where(
                BillingInvoice.status == status
            )

        statement = (
            statement
            .order_by(
                BillingInvoice.created_at.desc(),
                BillingInvoice.id.desc(),
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
    ) -> int:
        statement = select(func.count(BillingInvoice.id))

        if user_id is not None:
            statement = statement.where(
                BillingInvoice.user_id == user_id
            )

        if status is not None:
            statement = statement.where(
                BillingInvoice.status == status
            )

        return int(db.execute(statement).scalar_one())


billing_invoice_repository = BillingInvoiceRepository()