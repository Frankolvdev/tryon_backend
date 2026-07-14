from sqlalchemy.orm import Session

from app.common.billing_enums import BillingProvider
from app.models.billing_customer import BillingCustomer
from app.models.user import User
from app.repositories.billing_customer_repository import (
    billing_customer_repository,
)
from app.services.stripe_client_service import stripe_client_service


class BillingCustomerService:
    def get_or_create_stripe_customer(
        self,
        db: Session,
        *,
        user: User,
    ) -> BillingCustomer:
        existing = (
            billing_customer_repository.get_by_user_and_provider(
                db,
                user_id=user.id,
                provider=BillingProvider.STRIPE.value,
            )
        )

        user_name = getattr(user, "full_name", None)

        if existing:
            try:
                stripe_client_service.update_customer(
                    db,
                    customer_id=existing.provider_customer_id,
                    email=user.email,
                    name=user_name,
                    metadata={
                        "internal_user_id": str(user.id),
                    },
                )
            except Exception:
                pass

            if existing.email != user.email or existing.name != user_name:
                existing.email = user.email
                existing.name = user_name

                db.add(existing)
                db.commit()
                db.refresh(existing)

            return existing

        stripe_customer = stripe_client_service.create_customer(
            db,
            email=user.email,
            name=user_name,
            metadata={
                "internal_user_id": str(user.id),
            },
        )

        return billing_customer_repository.create(
            db,
            data={
                "user_id": user.id,
                "provider": BillingProvider.STRIPE.value,
                "provider_customer_id": stripe_customer.id,
                "email": user.email,
                "name": user_name,
            },
        )


billing_customer_service = BillingCustomerService()