from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.common.billing_enums import BillingInvoiceStatus


class BillingInvoiceResponse(BaseModel):
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


class BillingInvoiceListResponse(BaseModel):
    items: list[BillingInvoiceResponse]
    total: int
    skip: int
    limit: int