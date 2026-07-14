from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.common.billing_enums import (
    BillingInvoiceStatus,
    BillingPaymentStatus,
)


class BillingPaymentHistoryResponse(BaseModel):
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
    refundable_amount: Decimal

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


class BillingPaymentHistoryListResponse(BaseModel):
    items: list[BillingPaymentHistoryResponse]
    total: int
    skip: int
    limit: int


class BillingInvoiceHistoryResponse(BaseModel):
    id: int
    user_id: int
    billing_customer_id: int | None
    user_subscription_id: int | None
    billing_payment_id: int | None

    provider: str
    provider_invoice_id: str
    invoice_number: str | None
    status: BillingInvoiceStatus

    currency: str

    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total: Decimal
    amount_paid: Decimal

    hosted_invoice_url: str | None
    invoice_pdf_url: str | None

    period_start: datetime | None
    period_end: datetime | None
    due_at: datetime | None
    paid_at: datetime | None

    metadata: dict[str, Any]

    created_at: datetime
    updated_at: datetime


class BillingInvoiceHistoryListResponse(BaseModel):
    items: list[BillingInvoiceHistoryResponse]
    total: int
    skip: int
    limit: int


class BillingInvoiceDocumentResponse(BaseModel):
    invoice_id: int
    hosted_invoice_url: str | None
    invoice_pdf_url: str | None
    available: bool
    message: str


class BillingPaymentReconcileResponse(BaseModel):
    payment: BillingPaymentHistoryResponse
    reconciled: bool
    message: str


class BillingPaymentRefundRequest(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0)

    reason: str = Field(
        default="requested_by_customer",
        pattern=r"^(duplicate|fraudulent|requested_by_customer)$",
    )


class BillingPaymentRefundResponse(BaseModel):
    payment: BillingPaymentHistoryResponse
    stripe_refund_id: str
    refunded_amount: Decimal
    fully_refunded: bool
    message: str