from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.common.billing_enums import (
    BillingInterval,
    BillingProvider,
    SubscriptionStatus,
)


class SubscriptionCheckoutRequest(BaseModel):
    plan_key: str = Field(min_length=2, max_length=100)
    success_url: HttpUrl
    cancel_url: HttpUrl
    allow_promotion_codes: bool = True


class SubscriptionCheckoutResponse(BaseModel):
    checkout_session_id: str
    checkout_url: str
    customer_id: str
    plan_key: str


class SubscriptionCancelRequest(BaseModel):
    cancel_immediately: bool = False


class SubscriptionReactivateRequest(BaseModel):
    confirm: bool = True


class SubscriptionChangePlanRequest(BaseModel):
    new_plan_key: str = Field(min_length=2, max_length=100)

    proration_behavior: Literal[
        "always_invoice",
        "create_prorations",
        "none",
    ] = "create_prorations"


class SubscriptionPortalRequest(BaseModel):
    return_url: HttpUrl


class SubscriptionPortalResponse(BaseModel):
    portal_url: str


class UserSubscriptionResponse(BaseModel):
    id: int
    user_id: int
    subscription_plan_id: int
    billing_customer_id: int | None

    provider: BillingProvider
    provider_subscription_id: str | None
    status: SubscriptionStatus

    plan_key: str
    plan_name: str
    billing_interval: BillingInterval
    currency: str
    price_amount: str
    tokens_per_period: int
    priority: int
    features: list[str]

    current_period_start: datetime | None
    current_period_end: datetime | None

    trial_start: datetime | None
    trial_end: datetime | None

    cancel_at: datetime | None
    canceled_at: datetime | None
    ended_at: datetime | None
    cancel_at_period_end: bool

    last_tokens_granted_at: datetime | None
    metadata: dict[str, Any]

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubscriptionActionResponse(BaseModel):
    subscription: UserSubscriptionResponse
    message: str


class SubscriptionSyncResponse(BaseModel):
    subscription: UserSubscriptionResponse
    synchronized: bool
    message: str


class AdminSubscriptionListResponse(BaseModel):
    items: list[UserSubscriptionResponse]
    total: int
    skip: int
    limit: int