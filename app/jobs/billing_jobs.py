from collections.abc import Callable

from sqlalchemy.orm import Session

from app.common.time import utc_now
from app.schemas.billing_operations import BillingJobResult
from app.services.billing_maintenance_service import (
    billing_maintenance_service,
)


class BillingJobs:
    def synchronize_subscriptions(
        self,
        db: Session,
        *,
        max_items: int = 100,
    ) -> BillingJobResult:
        started_at = utc_now()

        result = (
            billing_maintenance_service.synchronize_subscriptions(
                db,
                limit=max_items,
            )
        )

        return BillingJobResult(
            job_name="billing.synchronize_subscriptions",
            started_at=started_at,
            completed_at=utc_now(),
            processed=result.processed,
            succeeded=result.succeeded,
            failed=result.failed,
            skipped=result.skipped,
            success=result.failed == 0,
            errors=result.errors,
        )

    def reconcile_token_purchases(
        self,
        db: Session,
        *,
        max_items: int = 100,
    ) -> BillingJobResult:
        started_at = utc_now()

        result = (
            billing_maintenance_service
            .reconcile_pending_token_purchases(
                db,
                limit=max_items,
            )
        )

        return BillingJobResult(
            job_name="billing.reconcile_token_purchases",
            started_at=started_at,
            completed_at=utc_now(),
            processed=result.processed,
            succeeded=result.succeeded,
            failed=result.failed,
            skipped=result.skipped,
            success=result.failed == 0,
            errors=result.errors,
        )

    def retry_failed_events(
        self,
        db: Session,
        *,
        max_items: int = 100,
    ) -> BillingJobResult:
        started_at = utc_now()

        result = (
            billing_maintenance_service
            .retry_failed_billing_events(
                db,
                limit=max_items,
            )
        )

        return BillingJobResult(
            job_name="billing.retry_failed_events",
            started_at=started_at,
            completed_at=utc_now(),
            processed=result.processed,
            succeeded=result.succeeded,
            failed=result.failed,
            skipped=result.skipped,
            success=result.failed == 0,
            errors=result.errors,
        )

    def expire_stale_checkouts(
        self,
        db: Session,
        *,
        max_items: int = 100,
    ) -> BillingJobResult:
        started_at = utc_now()

        result = (
            billing_maintenance_service.expire_stale_checkouts(
                db,
                limit=max_items,
            )
        )

        return BillingJobResult(
            job_name="billing.expire_stale_checkouts",
            started_at=started_at,
            completed_at=utc_now(),
            processed=result.processed,
            succeeded=result.succeeded,
            failed=result.failed,
            skipped=result.skipped,
            success=result.failed == 0,
            errors=result.errors,
        )

    def hourly_maintenance(
        self,
        db: Session,
        *,
        max_items: int = 100,
    ) -> BillingJobResult:
        started_at = utc_now()

        token_result = (
            billing_maintenance_service
            .reconcile_pending_token_purchases(
                db,
                limit=max_items,
            )
        )

        event_result = (
            billing_maintenance_service
            .retry_failed_billing_events(
                db,
                limit=max_items,
            )
        )

        checkout_result = (
            billing_maintenance_service.expire_stale_checkouts(
                db,
                limit=max_items,
            )
        )

        processed = (
            token_result.processed
            + event_result.processed
            + checkout_result.processed
        )

        succeeded = (
            token_result.succeeded
            + event_result.succeeded
            + checkout_result.succeeded
        )

        failed = (
            token_result.failed
            + event_result.failed
            + checkout_result.failed
        )

        skipped = (
            token_result.skipped
            + event_result.skipped
            + checkout_result.skipped
        )

        errors = [
            *token_result.errors,
            *event_result.errors,
            *checkout_result.errors,
        ]

        return BillingJobResult(
            job_name="billing.hourly_maintenance",
            started_at=started_at,
            completed_at=utc_now(),
            processed=processed,
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            success=failed == 0,
            errors=errors,
        )

    def daily_maintenance(
        self,
        db: Session,
        *,
        max_items: int = 500,
    ) -> BillingJobResult:
        started_at = utc_now()

        subscription_result = (
            billing_maintenance_service
            .synchronize_subscriptions(
                db,
                limit=max_items,
            )
        )

        token_result = (
            billing_maintenance_service
            .reconcile_pending_token_purchases(
                db,
                limit=max_items,
            )
        )

        event_result = (
            billing_maintenance_service
            .retry_failed_billing_events(
                db,
                limit=max_items,
            )
        )

        checkout_result = (
            billing_maintenance_service
            .expire_stale_checkouts(
                db,
                limit=max_items,
            )
        )

        processed = (
            subscription_result.processed
            + token_result.processed
            + event_result.processed
            + checkout_result.processed
        )

        succeeded = (
            subscription_result.succeeded
            + token_result.succeeded
            + event_result.succeeded
            + checkout_result.succeeded
        )

        failed = (
            subscription_result.failed
            + token_result.failed
            + event_result.failed
            + checkout_result.failed
        )

        skipped = (
            subscription_result.skipped
            + token_result.skipped
            + event_result.skipped
            + checkout_result.skipped
        )

        errors = [
            *subscription_result.errors,
            *token_result.errors,
            *event_result.errors,
            *checkout_result.errors,
        ]

        return BillingJobResult(
            job_name="billing.daily_maintenance",
            started_at=started_at,
            completed_at=utc_now(),
            processed=processed,
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            success=failed == 0,
            errors=errors,
        )


billing_jobs = BillingJobs()


BILLING_JOB_HANDLERS: dict[
    str,
    Callable[..., BillingJobResult],
] = {
    "billing.synchronize_subscriptions": (
        billing_jobs.synchronize_subscriptions
    ),
    "billing.reconcile_token_purchases": (
        billing_jobs.reconcile_token_purchases
    ),
    "billing.retry_failed_events": (
        billing_jobs.retry_failed_events
    ),
    "billing.expire_stale_checkouts": (
        billing_jobs.expire_stale_checkouts
    ),
    "billing.hourly_maintenance": (
        billing_jobs.hourly_maintenance
    ),
    "billing.daily_maintenance": (
        billing_jobs.daily_maintenance
    ),
}