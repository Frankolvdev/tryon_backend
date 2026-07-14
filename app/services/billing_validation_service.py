from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.billing_enums import BillingEventStatus
from app.common.enums import IntegrationProvider
from app.common.time import utc_now
from app.models.billing_event import BillingEvent
from app.models.subscription_plan import SubscriptionPlan
from app.models.token_package import TokenPackage
from app.schemas.billing_operations import (
    BillingValidationItem,
    BillingValidationResponse,
)
from app.services.integration_service import integration_service


class BillingValidationService:
    def _check(
        self,
        *,
        key: str,
        valid: bool,
        required: bool,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> BillingValidationItem:
        return BillingValidationItem(
            key=key,
            valid=valid,
            required=required,
            message=message,
            metadata=metadata or {},
        )

    def validate(self, db: Session) -> BillingValidationResponse:
        checks: list[BillingValidationItem] = []

        stripe_enabled = False
        stripe_api_key_configured = False
        stripe_webhook_secret_configured = False

        try:
            stripe_config = integration_service.get_config(
                db,
                IntegrationProvider.STRIPE,
            )

            stripe_enabled = bool(stripe_config.is_enabled)
            stripe_api_key_configured = bool(
                stripe_config.api_key
            )
            stripe_webhook_secret_configured = bool(
                stripe_config.webhook_secret
            )

            checks.append(
                self._check(
                    key="stripe_enabled",
                    valid=stripe_enabled,
                    required=True,
                    message=(
                        "Stripe integration is enabled."
                        if stripe_enabled
                        else "Stripe integration is disabled."
                    ),
                )
            )

            checks.append(
                self._check(
                    key="stripe_api_key",
                    valid=stripe_api_key_configured,
                    required=True,
                    message=(
                        "Stripe API key is configured."
                        if stripe_api_key_configured
                        else "Stripe API key is missing."
                    ),
                )
            )

            checks.append(
                self._check(
                    key="stripe_webhook_secret",
                    valid=stripe_webhook_secret_configured,
                    required=True,
                    message=(
                        "Stripe webhook secret is configured."
                        if stripe_webhook_secret_configured
                        else "Stripe webhook secret is missing."
                    ),
                )
            )

        except Exception as error:
            checks.append(
                self._check(
                    key="stripe_configuration",
                    valid=False,
                    required=True,
                    message=(
                        "Stripe integration configuration "
                        f"could not be loaded: {error}"
                    ),
                )
            )

        active_plan_count = int(
            db.execute(
                select(func.count(SubscriptionPlan.id)).where(
                    SubscriptionPlan.is_active.is_(True)
                )
            ).scalar_one()
        )

        public_plan_count = int(
            db.execute(
                select(func.count(SubscriptionPlan.id)).where(
                    SubscriptionPlan.is_active.is_(True),
                    SubscriptionPlan.is_public.is_(True),
                )
            ).scalar_one()
        )

        synchronized_plan_count = int(
            db.execute(
                select(func.count(SubscriptionPlan.id)).where(
                    SubscriptionPlan.is_active.is_(True),
                    SubscriptionPlan.stripe_product_id.is_not(None),
                    SubscriptionPlan.stripe_price_id.is_not(None),
                )
            ).scalar_one()
        )

        checks.append(
            self._check(
                key="active_subscription_plans",
                valid=active_plan_count > 0,
                required=True,
                message=(
                    f"{active_plan_count} active subscription "
                    "plan(s) found."
                    if active_plan_count > 0
                    else "No active subscription plans exist."
                ),
                metadata={
                    "active": active_plan_count,
                    "public": public_plan_count,
                    "stripe_synchronized": (
                        synchronized_plan_count
                    ),
                },
            )
        )

        plans_ready = (
            active_plan_count > 0
            and synchronized_plan_count == active_plan_count
        )

        checks.append(
            self._check(
                key="subscription_plans_stripe_sync",
                valid=plans_ready,
                required=True,
                message=(
                    "All active subscription plans are "
                    "synchronized with Stripe."
                    if plans_ready
                    else (
                        f"{synchronized_plan_count} of "
                        f"{active_plan_count} active plans are "
                        "synchronized with Stripe."
                    )
                ),
            )
        )

        active_token_package_count = int(
            db.execute(
                select(func.count(TokenPackage.id)).where(
                    TokenPackage.is_active.is_(True)
                )
            ).scalar_one()
        )

        checks.append(
            self._check(
                key="active_token_packages",
                valid=active_token_package_count > 0,
                required=False,
                message=(
                    f"{active_token_package_count} active token "
                    "package(s) found."
                    if active_token_package_count > 0
                    else (
                        "No active token packages exist. "
                        "Subscriptions can still operate."
                    )
                ),
            )
        )

        failed_event_count = int(
            db.execute(
                select(func.count(BillingEvent.id)).where(
                    BillingEvent.status
                    == BillingEventStatus.FAILED.value
                )
            ).scalar_one()
        )

        checks.append(
            self._check(
                key="failed_billing_events",
                valid=failed_event_count == 0,
                required=False,
                message=(
                    "No failed billing events are pending."
                    if failed_event_count == 0
                    else (
                        f"{failed_event_count} failed billing "
                        "event(s) require attention."
                    )
                ),
                metadata={
                    "failed_events": failed_event_count,
                },
            )
        )

        required_checks = [
            check
            for check in checks
            if check.required
        ]

        ready = bool(required_checks) and all(
            check.valid
            for check in required_checks
        )

        return BillingValidationResponse(
            ready=ready,
            stripe_enabled=stripe_enabled,
            checks=checks,
            checked_at=utc_now(),
        )


billing_validation_service = BillingValidationService()