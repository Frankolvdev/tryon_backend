from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class BillingRevenueMetricsResponse(BaseModel):
    currency: str

    gross_revenue: Decimal
    refunded_revenue: Decimal
    net_revenue: Decimal

    subscription_revenue: Decimal
    token_purchase_revenue: Decimal
    other_revenue: Decimal

    successful_payments: int
    failed_payments: int
    refunded_payments: int
    partially_refunded_payments: int

    period_start: datetime
    period_end: datetime


class BillingSubscriptionMetricsResponse(BaseModel):
    currency: str

    monthly_recurring_revenue: Decimal
    annual_recurring_revenue: Decimal

    active_subscriptions: int
    trialing_subscriptions: int
    past_due_subscriptions: int
    canceled_subscriptions: int
    unpaid_subscriptions: int

    new_subscriptions: int
    canceled_during_period: int

    subscriber_churn_rate: Decimal

    period_start: datetime
    period_end: datetime


class BillingTokenMetricsResponse(BaseModel):
    completed_purchases: int
    pending_purchases: int
    failed_purchases: int
    refunded_purchases: int

    tokens_sold: int
    bonus_tokens_granted: int
    total_tokens_granted: int

    period_start: datetime
    period_end: datetime


class BillingDashboardResponse(BaseModel):
    revenue: BillingRevenueMetricsResponse
    subscriptions: BillingSubscriptionMetricsResponse
    tokens: BillingTokenMetricsResponse

    generated_at: datetime


class BillingMaintenanceOptions(BaseModel):
    synchronize_subscriptions: bool = True
    reconcile_token_purchases: bool = True
    retry_failed_events: bool = True
    expire_stale_checkouts: bool = True

    max_items_per_task: int = Field(
        default=100,
        ge=1,
        le=1000,
    )


class BillingMaintenanceTaskResult(BaseModel):
    task: str
    processed: int
    succeeded: int
    failed: int
    skipped: int
    errors: list[dict[str, Any]] = Field(default_factory=list)


class BillingMaintenanceResponse(BaseModel):
    started_at: datetime
    completed_at: datetime

    tasks: list[BillingMaintenanceTaskResult]

    total_processed: int
    total_succeeded: int
    total_failed: int
    total_skipped: int

    success: bool