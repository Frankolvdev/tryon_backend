from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.billing_enums import (
    BillingEventStatus, BillingInvoiceStatus, BillingPaymentStatus,
    SubscriptionStatus, TokenPurchaseStatus,
)
from app.common.time import utc_now
from app.models.billing_event import BillingEvent
from app.models.billing_invoice import BillingInvoice
from app.models.billing_payment import BillingPayment
from app.models.token_purchase import TokenPurchase
from app.models.user_subscription import UserSubscription
from app.schemas.billing_operations import BillingOperationsOverview


class BillingOperationsOverviewService:
    def _count(self, db: Session, model, *conditions) -> int:
        return int(db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0)

    def get(self, db: Session) -> BillingOperationsOverview:
        revenue = db.execute(
            select(
                func.coalesce(func.sum(BillingPayment.amount), 0),
                func.coalesce(func.sum(BillingPayment.refunded_amount), 0),
                func.min(BillingPayment.currency),
            ).where(BillingPayment.status.in_([
                BillingPaymentStatus.SUCCEEDED.value,
                BillingPaymentStatus.REFUNDED.value,
                BillingPaymentStatus.PARTIALLY_REFUNDED.value,
            ]))
        ).one()
        return BillingOperationsOverview(
            active_subscriptions=self._count(db, UserSubscription, UserSubscription.status.in_([SubscriptionStatus.ACTIVE.value, SubscriptionStatus.TRIALING.value])),
            subscriptions_needing_attention=self._count(db, UserSubscription, UserSubscription.status.in_([SubscriptionStatus.PAST_DUE.value, SubscriptionStatus.UNPAID.value, SubscriptionStatus.INCOMPLETE.value])),
            pending_token_purchases=self._count(db, TokenPurchase, TokenPurchase.status.in_([TokenPurchaseStatus.PENDING.value, TokenPurchaseStatus.PAID.value])),
            failed_token_purchases=self._count(db, TokenPurchase, TokenPurchase.status == TokenPurchaseStatus.FAILED.value),
            failed_billing_events=self._count(db, BillingEvent, BillingEvent.status == BillingEventStatus.FAILED.value),
            open_invoices=self._count(db, BillingInvoice, BillingInvoice.status.in_([BillingInvoiceStatus.DRAFT.value, BillingInvoiceStatus.OPEN.value, BillingInvoiceStatus.UNCOLLECTIBLE.value])),
            failed_payments=self._count(db, BillingPayment, BillingPayment.status == BillingPaymentStatus.FAILED.value),
            succeeded_revenue_amount=float(revenue[0] or 0),
            refunded_amount=float(revenue[1] or 0),
            currency=(revenue[2] or 'USD').upper(),
            generated_at=utc_now(),
        )


billing_operations_overview_service = BillingOperationsOverviewService()
