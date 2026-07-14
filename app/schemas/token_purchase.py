from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.common.billing_enums import (
    BillingPaymentStatus,
    TokenPurchaseStatus,
)


class TokenPurchaseCheckoutRequest(BaseModel):
    token_package_id: int
    success_url: HttpUrl
    cancel_url: HttpUrl
    allow_promotion_codes: bool = True


class TokenPurchaseCheckoutResponse(BaseModel):
    token_purchase_id: int
    billing_payment_id: int
    checkout_session_id: str
    checkout_url: str
    status: TokenPurchaseStatus


class TokenPurchaseResponse(BaseModel):
    id: int
    user_id: int
    token_package_id: int
    billing_payment_id: int | None

    status: TokenPurchaseStatus

    tokens_amount: int
    bonus_tokens: int
    total_tokens: int

    currency: str
    amount: Decimal

    provider_checkout_session_id: str | None
    provider_payment_intent_id: str | None
    token_transaction_id: int | None

    metadata: dict[str, Any]

    paid_at: datetime | None
    credited_at: datetime | None
    refunded_at: datetime | None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BillingPaymentResponse(BaseModel):
    id: int
    user_id: int
    billing_customer_id: int | None
    user_subscription_id: int | None

    provider: str
    payment_type: str
    status: BillingPaymentStatus

    currency: str
    amount: Decimal
    refunded_amount: Decimal

    provider_payment_intent_id: str | None
    provider_charge_id: str | None
    provider_checkout_session_id: str | None

    failure_code: str | None
    failure_message: str | None
    description: str | None

    metadata: dict[str, Any]

    paid_at: datetime | None
    failed_at: datetime | None
    refunded_at: datetime | None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenPurchaseDetailResponse(BaseModel):
    purchase: TokenPurchaseResponse
    payment: BillingPaymentResponse | None


class TokenPurchaseListResponse(BaseModel):
    items: list[TokenPurchaseResponse]
    total: int
    skip: int
    limit: int


class TokenPurchaseReconcileRequest(BaseModel):
    force: bool = False


class TokenPurchaseReconcileResponse(BaseModel):
    purchase: TokenPurchaseResponse
    payment: BillingPaymentResponse | None
    reconciled: bool
    message: str


class TokenPurchaseRefundRequest(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0)

    reason: str = Field(
        default="requested_by_customer",
        pattern=r"^(duplicate|fraudulent|requested_by_customer)$",
    )

    remove_tokens: bool = True


class TokenPurchaseRefundResponse(BaseModel):
    purchase: TokenPurchaseResponse
    payment: BillingPaymentResponse
    stripe_refund_id: str
    refunded_amount: Decimal
    removed_tokens: int
    message: str