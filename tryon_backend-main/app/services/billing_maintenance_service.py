from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.billing_enums import (
    BillingEventStatus,
    SubscriptionStatus,
    TokenPurchaseStatus,
)
from app.common.time import utc_now
from app.models.billing_event import BillingEvent
from app.models.token_purchase import TokenPurchase
from app.models.user_subscription import UserSubscription
from app.schemas.billing_analytics import (
    BillingMaintenanceOptions,
    BillingMaintenanceResponse,
    BillingMaintenanceTaskResult,
)
from app.services.billing_event_service import (
    billing_event_service,
)
from app.services.stripe_client_service import (
    stripe_client_service,
)
from app.services.subscription_service import (
    subscription_service,
)
from app.services.token_purchase_service import (
    token_purchase_service,
)


class BillingMaintenanceService:
    def _result(
        self,
        *,
        task: str,
        processed: int,
        succeeded: int,
        failed: int,
        skipped: int,
        errors: list[dict],
    ) -> BillingMaintenanceTaskResult:
        return BillingMaintenanceTaskResult(
            task=task,
            processed=processed,
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            errors=errors,
        )

    def synchronize_subscriptions(
        self,
        db: Session,
        *,
        limit: int,
    ) -> BillingMaintenanceTaskResult:
        statement = (
            select(UserSubscription)
            .where(
                UserSubscription.provider_subscription_id
                .is_not(None)
            )
            .where(
                UserSubscription.status.in_(
                    [
                        SubscriptionStatus.INCOMPLETE.value,
                        SubscriptionStatus.TRIALING.value,
                        SubscriptionStatus.ACTIVE.value,
                        SubscriptionStatus.PAST_DUE.value,
                        SubscriptionStatus.UNPAID.value,
                        SubscriptionStatus.PAUSED.value,
                    ]
                )
            )
            .order_by(
                UserSubscription.updated_at.asc()
            )
            .limit(limit)
        )

        subscriptions = list(
            db.execute(statement).scalars().all()
        )

        succeeded = 0
        failed = 0
        skipped = 0
        errors: list[dict] = []

        for subscription in subscriptions:
            if not subscription.provider_subscription_id:
                skipped += 1
                continue

            try:
                stripe_subscription = (
                    stripe_client_service
                    .retrieve_subscription(
                        db,
                        subscription_id=(
                            subscription
                            .provider_subscription_id
                        ),
                    )
                )

                subscription_service.sync_from_stripe_object(
                    db,
                    stripe_subscription=stripe_subscription,
                )

                succeeded += 1

            except Exception as error:
                db.rollback()
                failed += 1

                errors.append(
                    {
                        "subscription_id": subscription.id,
                        "provider_subscription_id": (
                            subscription
                            .provider_subscription_id
                        ),
                        "error": str(error),
                    }
                )

        return self._result(
            task="synchronize_subscriptions",
            processed=len(subscriptions),
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            errors=errors,
        )

    def reconcile_pending_token_purchases(
        self,
        db: Session,
        *,
        limit: int,
    ) -> BillingMaintenanceTaskResult:
        statement = (
            select(TokenPurchase)
            .where(
                TokenPurchase.status.in_(
                    [
                        TokenPurchaseStatus.PENDING.value,
                        TokenPurchaseStatus.PAID.value,
                    ]
                )
            )
            .where(
                TokenPurchase.provider_checkout_session_id
                .is_not(None)
            )
            .order_by(TokenPurchase.created_at.asc())
            .limit(limit)
        )

        purchases = list(
            db.execute(statement).scalars().all()
        )

        succeeded = 0
        failed = 0
        skipped = 0
        errors: list[dict] = []

        for purchase in purchases:
            try:
                result = token_purchase_service.reconcile(
                    db,
                    purchase_id=purchase.id,
                    force=False,
                )

                if result.reconciled:
                    succeeded += 1
                else:
                    skipped += 1

            except Exception as error:
                db.rollback()
                failed += 1

                errors.append(
                    {
                        "token_purchase_id": purchase.id,
                        "checkout_session_id": (
                            purchase
                            .provider_checkout_session_id
                        ),
                        "error": str(error),
                    }
                )

        return self._result(
            task="reconcile_pending_token_purchases",
            processed=len(purchases),
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            errors=errors,
        )

    def retry_failed_billing_events(
        self,
        db: Session,
        *,
        limit: int,
    ) -> BillingMaintenanceTaskResult:
        statement = (
            select(BillingEvent)
            .where(
                BillingEvent.status
                == BillingEventStatus.FAILED.value
            )
            .where(BillingEvent.processing_attempts < 5)
            .order_by(BillingEvent.updated_at.asc())
            .limit(limit)
        )

        events = list(
            db.execute(statement).scalars().all()
        )

        succeeded = 0
        failed = 0
        skipped = 0
        errors: list[dict] = []

        for event in events:
            try:
                result = billing_event_service.retry_event(
                    db,
                    event_id=event.id,
                )

                if result.retried:
                    succeeded += 1
                else:
                    skipped += 1

            except Exception as error:
                db.rollback()
                failed += 1

                errors.append(
                    {
                        "billing_event_id": event.id,
                        "provider_event_id": (
                            event.provider_event_id
                        ),
                        "event_type": event.event_type,
                        "error": str(error),
                    }
                )

        return self._result(
            task="retry_failed_billing_events",
            processed=len(events),
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            errors=errors,
        )

    def expire_stale_checkouts(
        self,
        db: Session,
        *,
        limit: int,
    ) -> BillingMaintenanceTaskResult:
        stale_before = utc_now() - timedelta(hours=24)

        statement = (
            select(TokenPurchase)
            .where(
                TokenPurchase.status
                == TokenPurchaseStatus.PENDING.value
            )
            .where(
                TokenPurchase.provider_checkout_session_id
                .is_not(None)
            )
            .where(TokenPurchase.created_at < stale_before)
            .order_by(TokenPurchase.created_at.asc())
            .limit(limit)
        )

        purchases = list(
            db.execute(statement).scalars().all()
        )

        succeeded = 0
        failed = 0
        skipped = 0
        errors: list[dict] = []

        for purchase in purchases:
            try:
                checkout_session = (
                    stripe_client_service
                    .retrieve_checkout_session(
                        db,
                        checkout_session_id=(
                            purchase
                            .provider_checkout_session_id
                        ),
                    )
                )

                checkout_status = getattr(
                    checkout_session,
                    "status",
                    None,
                )

                payment_status = getattr(
                    checkout_session,
                    "payment_status",
                    None,
                )

                if payment_status == "paid":
                    token_purchase_service.process_checkout_completed(
                        db,
                        checkout_session=checkout_session,
                    )

                    succeeded += 1
                    continue

                if checkout_status == "open":
                    stripe_client_service.expire_checkout_session(
                        db,
                        checkout_session_id=(
                            purchase
                            .provider_checkout_session_id
                        ),
                    )

                token_purchase_service.mark_checkout_failed(
                    db,
                    checkout_session=checkout_session,
                    error_message=(
                        "Stale Stripe Checkout Session expired "
                        "by billing maintenance."
                    ),
                )

                succeeded += 1

            except Exception as error:
                db.rollback()
                failed += 1

                errors.append(
                    {
                        "token_purchase_id": purchase.id,
                        "checkout_session_id": (
                            purchase
                            .provider_checkout_session_id
                        ),
                        "error": str(error),
                    }
                )

        return self._result(
            task="expire_stale_checkouts",
            processed=len(purchases),
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            errors=errors,
        )

    def run(
        self,
        db: Session,
        *,
        options: BillingMaintenanceOptions,
    ) -> BillingMaintenanceResponse:
        started_at = utc_now()
        results: list[BillingMaintenanceTaskResult] = []

        if options.synchronize_subscriptions:
            results.append(
                self.synchronize_subscriptions(
                    db,
                    limit=options.max_items_per_task,
                )
            )

        if options.reconcile_token_purchases:
            results.append(
                self.reconcile_pending_token_purchases(
                    db,
                    limit=options.max_items_per_task,
                )
            )

        if options.retry_failed_events:
            results.append(
                self.retry_failed_billing_events(
                    db,
                    limit=options.max_items_per_task,
                )
            )

        if options.expire_stale_checkouts:
            results.append(
                self.expire_stale_checkouts(
                    db,
                    limit=options.max_items_per_task,
                )
            )

        total_processed = sum(
            item.processed for item in results
        )

        total_succeeded = sum(
            item.succeeded for item in results
        )

        total_failed = sum(
            item.failed for item in results
        )

        total_skipped = sum(
            item.skipped for item in results
        )

        return BillingMaintenanceResponse(
            started_at=started_at,
            completed_at=utc_now(),
            tasks=results,
            total_processed=total_processed,
            total_succeeded=total_succeeded,
            total_failed=total_failed,
            total_skipped=total_skipped,
            success=total_failed == 0,
        )


billing_maintenance_service = BillingMaintenanceService()