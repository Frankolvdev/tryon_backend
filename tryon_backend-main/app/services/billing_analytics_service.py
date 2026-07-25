from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.common.billing_enums import (
    BillingInterval,
    BillingPaymentStatus,
    BillingPaymentType,
    SubscriptionStatus,
    TokenPurchaseStatus,
)
from app.common.time import utc_now
from app.models.billing_payment import BillingPayment
from app.models.subscription_plan import SubscriptionPlan
from app.models.token_purchase import TokenPurchase
from app.models.user_subscription import UserSubscription
from app.schemas.billing_analytics import (
    BillingDashboardResponse,
    BillingRevenueMetricsResponse,
    BillingSubscriptionMetricsResponse,
    BillingTokenMetricsResponse,
)


class BillingAnalyticsService:
    def _money(self, value) -> Decimal:
        return Decimal(value or 0).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    def _percentage(
        self,
        numerator: int,
        denominator: int,
    ) -> Decimal:
        if denominator <= 0:
            return Decimal("0.00")

        return (
            Decimal(numerator)
            / Decimal(denominator)
            * Decimal("100")
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    def _resolve_period(
        self,
        *,
        start: datetime | None,
        end: datetime | None,
    ) -> tuple[datetime, datetime]:
        resolved_end = end or utc_now()
        resolved_start = start or (
            resolved_end - timedelta(days=30)
        )

        if resolved_start >= resolved_end:
            raise ValueError(
                "Billing analytics start date must be earlier "
                "than the end date."
            )

        return resolved_start, resolved_end

    def _payment_sum(
        self,
        db: Session,
        *,
        start: datetime,
        end: datetime,
        payment_types: list[str] | None = None,
    ) -> Decimal:
        statement = (
            select(
                func.coalesce(
                    func.sum(BillingPayment.amount),
                    0,
                )
            )
            .where(
                BillingPayment.status.in_(
                    [
                        BillingPaymentStatus.SUCCEEDED.value,
                        BillingPaymentStatus.PARTIALLY_REFUNDED.value,
                        BillingPaymentStatus.REFUNDED.value,
                    ]
                )
            )
            .where(BillingPayment.created_at >= start)
            .where(BillingPayment.created_at < end)
        )

        if payment_types:
            statement = statement.where(
                BillingPayment.payment_type.in_(payment_types)
            )

        return self._money(db.execute(statement).scalar_one())

    def _refund_sum(
        self,
        db: Session,
        *,
        start: datetime,
        end: datetime,
    ) -> Decimal:
        statement = (
            select(
                func.coalesce(
                    func.sum(BillingPayment.refunded_amount),
                    0,
                )
            )
            .where(BillingPayment.created_at >= start)
            .where(BillingPayment.created_at < end)
        )

        return self._money(db.execute(statement).scalar_one())

    def _payment_count(
        self,
        db: Session,
        *,
        start: datetime,
        end: datetime,
        statuses: list[str],
    ) -> int:
        statement = (
            select(func.count(BillingPayment.id))
            .where(BillingPayment.status.in_(statuses))
            .where(BillingPayment.created_at >= start)
            .where(BillingPayment.created_at < end)
        )

        return int(db.execute(statement).scalar_one())

    def revenue_metrics(
        self,
        db: Session,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        currency: str = "USD",
    ) -> BillingRevenueMetricsResponse:
        period_start, period_end = self._resolve_period(
            start=start,
            end=end,
        )

        normalized_currency = currency.upper()

        base_query = [
            BillingPayment.currency == normalized_currency,
            BillingPayment.created_at >= period_start,
            BillingPayment.created_at < period_end,
        ]

        gross_statement = select(
            func.coalesce(func.sum(BillingPayment.amount), 0)
        ).where(
            *base_query,
            BillingPayment.status.in_(
                [
                    BillingPaymentStatus.SUCCEEDED.value,
                    BillingPaymentStatus.PARTIALLY_REFUNDED.value,
                    BillingPaymentStatus.REFUNDED.value,
                ]
            ),
        )

        refund_statement = select(
            func.coalesce(
                func.sum(BillingPayment.refunded_amount),
                0,
            )
        ).where(*base_query)

        gross_revenue = self._money(
            db.execute(gross_statement).scalar_one()
        )

        refunded_revenue = self._money(
            db.execute(refund_statement).scalar_one()
        )

        subscription_statement = select(
            func.coalesce(func.sum(BillingPayment.amount), 0)
        ).where(
            *base_query,
            BillingPayment.payment_type.in_(
                [
                    BillingPaymentType.SUBSCRIPTION.value,
                    BillingPaymentType.SUBSCRIPTION_RENEWAL.value,
                ]
            ),
            BillingPayment.status.in_(
                [
                    BillingPaymentStatus.SUCCEEDED.value,
                    BillingPaymentStatus.PARTIALLY_REFUNDED.value,
                    BillingPaymentStatus.REFUNDED.value,
                ]
            ),
        )

        token_statement = select(
            func.coalesce(func.sum(BillingPayment.amount), 0)
        ).where(
            *base_query,
            BillingPayment.payment_type
            == BillingPaymentType.TOKEN_PURCHASE.value,
            BillingPayment.status.in_(
                [
                    BillingPaymentStatus.SUCCEEDED.value,
                    BillingPaymentStatus.PARTIALLY_REFUNDED.value,
                    BillingPaymentStatus.REFUNDED.value,
                ]
            ),
        )

        subscription_revenue = self._money(
            db.execute(subscription_statement).scalar_one()
        )

        token_purchase_revenue = self._money(
            db.execute(token_statement).scalar_one()
        )

        other_revenue = (
            gross_revenue
            - subscription_revenue
            - token_purchase_revenue
        ).quantize(Decimal("0.01"))

        successful_payments = self._payment_count(
            db,
            start=period_start,
            end=period_end,
            statuses=[
                BillingPaymentStatus.SUCCEEDED.value,
            ],
        )

        failed_payments = self._payment_count(
            db,
            start=period_start,
            end=period_end,
            statuses=[
                BillingPaymentStatus.FAILED.value,
            ],
        )

        refunded_payments = self._payment_count(
            db,
            start=period_start,
            end=period_end,
            statuses=[
                BillingPaymentStatus.REFUNDED.value,
            ],
        )

        partially_refunded_payments = self._payment_count(
            db,
            start=period_start,
            end=period_end,
            statuses=[
                BillingPaymentStatus.PARTIALLY_REFUNDED.value,
            ],
        )

        return BillingRevenueMetricsResponse(
            currency=normalized_currency,
            gross_revenue=gross_revenue,
            refunded_revenue=refunded_revenue,
            net_revenue=(
                gross_revenue - refunded_revenue
            ).quantize(Decimal("0.01")),
            subscription_revenue=subscription_revenue,
            token_purchase_revenue=token_purchase_revenue,
            other_revenue=other_revenue,
            successful_payments=successful_payments,
            failed_payments=failed_payments,
            refunded_payments=refunded_payments,
            partially_refunded_payments=(
                partially_refunded_payments
            ),
            period_start=period_start,
            period_end=period_end,
        )

    def _subscription_status_count(
        self,
        db: Session,
        *,
        status: str,
    ) -> int:
        statement = select(
            func.count(UserSubscription.id)
        ).where(
            UserSubscription.status == status
        )

        return int(db.execute(statement).scalar_one())

    def subscription_metrics(
        self,
        db: Session,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        currency: str = "USD",
    ) -> BillingSubscriptionMetricsResponse:
        period_start, period_end = self._resolve_period(
            start=start,
            end=end,
        )

        normalized_currency = currency.upper()

        monthly_value = case(
            (
                SubscriptionPlan.billing_interval
                == BillingInterval.YEAR.value,
                SubscriptionPlan.price_amount
                / Decimal("12"),
            ),
            else_=SubscriptionPlan.price_amount,
        )

        mrr_statement = (
            select(
                func.coalesce(
                    func.sum(monthly_value),
                    0,
                )
            )
            .select_from(UserSubscription)
            .join(
                SubscriptionPlan,
                SubscriptionPlan.id
                == UserSubscription.subscription_plan_id,
            )
            .where(
                UserSubscription.status.in_(
                    [
                        SubscriptionStatus.ACTIVE.value,
                        SubscriptionStatus.PAST_DUE.value,
                    ]
                )
            )
            .where(
                SubscriptionPlan.currency
                == normalized_currency
            )
        )

        monthly_recurring_revenue = self._money(
            db.execute(mrr_statement).scalar_one()
        )

        active_subscriptions = self._subscription_status_count(
            db,
            status=SubscriptionStatus.ACTIVE.value,
        )

        trialing_subscriptions = self._subscription_status_count(
            db,
            status=SubscriptionStatus.TRIALING.value,
        )

        past_due_subscriptions = self._subscription_status_count(
            db,
            status=SubscriptionStatus.PAST_DUE.value,
        )

        canceled_subscriptions = self._subscription_status_count(
            db,
            status=SubscriptionStatus.CANCELED.value,
        )

        unpaid_subscriptions = self._subscription_status_count(
            db,
            status=SubscriptionStatus.UNPAID.value,
        )

        new_statement = (
            select(func.count(UserSubscription.id))
            .where(
                UserSubscription.created_at >= period_start
            )
            .where(
                UserSubscription.created_at < period_end
            )
        )

        canceled_statement = (
            select(func.count(UserSubscription.id))
            .where(
                UserSubscription.canceled_at.is_not(None)
            )
            .where(
                UserSubscription.canceled_at >= period_start
            )
            .where(
                UserSubscription.canceled_at < period_end
            )
        )

        start_base_statement = (
            select(func.count(UserSubscription.id))
            .where(
                UserSubscription.created_at < period_start
            )
            .where(
                (
                    UserSubscription.ended_at.is_(None)
                )
                | (
                    UserSubscription.ended_at >= period_start
                )
            )
        )

        new_subscriptions = int(
            db.execute(new_statement).scalar_one()
        )

        canceled_during_period = int(
            db.execute(canceled_statement).scalar_one()
        )

        subscribers_at_start = int(
            db.execute(start_base_statement).scalar_one()
        )

        return BillingSubscriptionMetricsResponse(
            currency=normalized_currency,
            monthly_recurring_revenue=(
                monthly_recurring_revenue
            ),
            annual_recurring_revenue=(
                monthly_recurring_revenue * Decimal("12")
            ).quantize(Decimal("0.01")),
            active_subscriptions=active_subscriptions,
            trialing_subscriptions=trialing_subscriptions,
            past_due_subscriptions=past_due_subscriptions,
            canceled_subscriptions=canceled_subscriptions,
            unpaid_subscriptions=unpaid_subscriptions,
            new_subscriptions=new_subscriptions,
            canceled_during_period=canceled_during_period,
            subscriber_churn_rate=self._percentage(
                canceled_during_period,
                subscribers_at_start,
            ),
            period_start=period_start,
            period_end=period_end,
        )

    def token_metrics(
        self,
        db: Session,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> BillingTokenMetricsResponse:
        period_start, period_end = self._resolve_period(
            start=start,
            end=end,
        )

        base_filters = [
            TokenPurchase.created_at >= period_start,
            TokenPurchase.created_at < period_end,
        ]

        count_statement = select(
            TokenPurchase.status,
            func.count(TokenPurchase.id),
        ).where(
            *base_filters
        ).group_by(
            TokenPurchase.status
        )

        status_counts = {
            status: int(count)
            for status, count in db.execute(
                count_statement
            ).all()
        }

        token_statement = select(
            func.coalesce(
                func.sum(TokenPurchase.tokens_amount),
                0,
            ),
            func.coalesce(
                func.sum(TokenPurchase.bonus_tokens),
                0,
            ),
        ).where(
            *base_filters,
            TokenPurchase.status.in_(
                [
                    TokenPurchaseStatus.CREDITED.value,
                    TokenPurchaseStatus.REFUNDED.value,
                ]
            ),
        )

        tokens_sold, bonus_tokens = db.execute(
            token_statement
        ).one()

        tokens_sold = int(tokens_sold or 0)
        bonus_tokens = int(bonus_tokens or 0)

        return BillingTokenMetricsResponse(
            completed_purchases=status_counts.get(
                TokenPurchaseStatus.CREDITED.value,
                0,
            ),
            pending_purchases=status_counts.get(
                TokenPurchaseStatus.PENDING.value,
                0,
            )
            + status_counts.get(
                TokenPurchaseStatus.PAID.value,
                0,
            ),
            failed_purchases=status_counts.get(
                TokenPurchaseStatus.FAILED.value,
                0,
            ),
            refunded_purchases=status_counts.get(
                TokenPurchaseStatus.REFUNDED.value,
                0,
            ),
            tokens_sold=tokens_sold,
            bonus_tokens_granted=bonus_tokens,
            total_tokens_granted=(
                tokens_sold + bonus_tokens
            ),
            period_start=period_start,
            period_end=period_end,
        )

    def dashboard(
        self,
        db: Session,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        currency: str = "USD",
    ) -> BillingDashboardResponse:
        return BillingDashboardResponse(
            revenue=self.revenue_metrics(
                db,
                start=start,
                end=end,
                currency=currency,
            ),
            subscriptions=self.subscription_metrics(
                db,
                start=start,
                end=end,
                currency=currency,
            ),
            tokens=self.token_metrics(
                db,
                start=start,
                end=end,
            ),
            generated_at=utc_now(),
        )


billing_analytics_service = BillingAnalyticsService()