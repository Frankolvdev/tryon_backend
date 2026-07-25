from typing import Any

from pydantic import BaseModel, Field


class StripeCheckoutTokenPurchaseRequest(BaseModel):
    token_package_id: int
    success_url: str = Field(min_length=5)
    cancel_url: str = Field(min_length=5)


class StripeCheckoutSubscriptionRequest(BaseModel):
    subscription_plan_key: str = Field(min_length=2)
    success_url: str = Field(min_length=5)
    cancel_url: str = Field(min_length=5)


class StripeCustomerPortalRequest(BaseModel):
    return_url: str = Field(min_length=5)


class StripeCheckoutResponse(BaseModel):
    checkout_session_id: str
    checkout_url: str


class StripeCustomerPortalResponse(BaseModel):
    portal_url: str


class StripeWebhookResult(BaseModel):
    received: bool
    event_type: str
    message: str = "Stripe webhook processed successfully."
    metadata: dict[str, Any] = {}