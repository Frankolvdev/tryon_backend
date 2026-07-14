from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.billing_customer import BillingCustomer
from app.repositories.base import BaseRepository


class BillingCustomerRepository(BaseRepository[BillingCustomer]):
    def __init__(self):
        super().__init__(BillingCustomer)

    def get_by_user_and_provider(
        self,
        db: Session,
        *,
        user_id: int,
        provider: str,
    ) -> BillingCustomer | None:
        statement = (
            select(BillingCustomer)
            .where(BillingCustomer.user_id == user_id)
            .where(BillingCustomer.provider == provider)
        )

        return db.execute(statement).scalar_one_or_none()

    def get_by_provider_customer_id(
        self,
        db: Session,
        *,
        provider: str,
        provider_customer_id: str,
    ) -> BillingCustomer | None:
        statement = (
            select(BillingCustomer)
            .where(BillingCustomer.provider == provider)
            .where(
                BillingCustomer.provider_customer_id
                == provider_customer_id
            )
        )

        return db.execute(statement).scalar_one_or_none()


billing_customer_repository = BillingCustomerRepository()