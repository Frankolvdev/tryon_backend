from sqlalchemy.orm import Session

from app.common.exceptions import NotFoundException
from app.jobs.billing_jobs import BILLING_JOB_HANDLERS
from app.schemas.billing_operations import (
    BillingJobResult,
    BillingJobsCatalogItem,
    BillingJobsCatalogResponse,
)


class BillingJobService:
    def catalog(self) -> BillingJobsCatalogResponse:
        return BillingJobsCatalogResponse(
            jobs=[
                BillingJobsCatalogItem(
                    name="billing.hourly_maintenance",
                    description=(
                        "Reconciles token purchases, retries "
                        "failed Stripe events and expires stale "
                        "Checkout Sessions."
                    ),
                    recommended_schedule="0 * * * *",
                    enabled=True,
                ),
                BillingJobsCatalogItem(
                    name="billing.daily_maintenance",
                    description=(
                        "Synchronizes subscriptions and runs all "
                        "Billing recovery tasks."
                    ),
                    recommended_schedule="15 3 * * *",
                    enabled=True,
                ),
                BillingJobsCatalogItem(
                    name=(
                        "billing.synchronize_subscriptions"
                    ),
                    description=(
                        "Synchronizes local subscriptions with "
                        "their current state in Stripe."
                    ),
                    recommended_schedule="0 */6 * * *",
                    enabled=True,
                ),
                BillingJobsCatalogItem(
                    name=(
                        "billing.reconcile_token_purchases"
                    ),
                    description=(
                        "Reconciles pending token purchases "
                        "against Stripe Checkout."
                    ),
                    recommended_schedule="*/15 * * * *",
                    enabled=True,
                ),
                BillingJobsCatalogItem(
                    name="billing.retry_failed_events",
                    description=(
                        "Retries failed Stripe billing events "
                        "with fewer than five attempts."
                    ),
                    recommended_schedule="*/10 * * * *",
                    enabled=True,
                ),
                BillingJobsCatalogItem(
                    name="billing.expire_stale_checkouts",
                    description=(
                        "Expires unpaid token Checkout Sessions "
                        "older than 24 hours."
                    ),
                    recommended_schedule="30 * * * *",
                    enabled=True,
                ),
            ]
        )

    def run(
        self,
        db: Session,
        *,
        job_name: str,
        max_items: int,
    ) -> BillingJobResult:
        handler = BILLING_JOB_HANDLERS.get(job_name)

        if not handler:
            raise NotFoundException(
                "Billing job handler not found."
            )

        return handler(
            db,
            max_items=max_items,
        )


billing_job_service = BillingJobService()