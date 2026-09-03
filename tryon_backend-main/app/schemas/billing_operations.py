from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BillingJobRunRequest(BaseModel):
    max_items: int = Field(
        default=100,
        ge=1,
        le=1000,
    )


class BillingJobResult(BaseModel):
    job_name: str
    started_at: datetime
    completed_at: datetime

    processed: int
    succeeded: int
    failed: int
    skipped: int

    success: bool
    errors: list[dict[str, Any]] = Field(default_factory=list)


class BillingValidationItem(BaseModel):
    key: str
    valid: bool
    required: bool
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class BillingValidationResponse(BaseModel):
    ready: bool
    stripe_enabled: bool
    checks: list[BillingValidationItem]
    checked_at: datetime


class BillingJobsCatalogItem(BaseModel):
    name: str
    description: str
    recommended_schedule: str
    enabled: bool


class BillingJobsCatalogResponse(BaseModel):
    jobs: list[BillingJobsCatalogItem]

class BillingOperationsOverview(BaseModel):
    active_subscriptions: int
    subscriptions_needing_attention: int
    pending_token_purchases: int
    failed_token_purchases: int
    failed_billing_events: int
    open_invoices: int
    failed_payments: int
    succeeded_revenue_amount: float
    refunded_amount: float
    currency: str
    generated_at: datetime
