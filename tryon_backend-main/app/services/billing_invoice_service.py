import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.common.billing_enums import (
    BillingInvoiceStatus,
    BillingPaymentStatus,
    BillingPaymentType,
    BillingProvider,
    SubscriptionStatus,
)
from app.common.time import utc_now
from app.models.billing_invoice import BillingInvoice
from app.models.billing_payment import BillingPayment
from app.repositories.billing_customer_repository import (
    billing_customer_repository,
)
from app.repositories.billing_invoice_repository import (
    billing_invoice_repository,
)
from app.repositories.billing_payment_repository import (
    billing_payment_repository,
)
from app.repositories.user_subscription_repository import (
    user_subscription_repository,
)
from app.schemas.billing_invoice import (
    BillingInvoiceListResponse,
    BillingInvoiceResponse,
)


class BillingInvoiceService:
    def _stripe_value(
        self,
        obj: Any,
        key: str,
        default: Any = None,
    ) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)

        return getattr(obj, key, default)

    def _stripe_id(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return self._stripe_value(value, "id")

    def provider_subscription_id(self, stripe_invoice: Any) -> str | None:
        direct = self._stripe_id(
            self._stripe_value(stripe_invoice, "subscription")
        )
        if direct:
            return direct

        parent = self._stripe_value(stripe_invoice, "parent", {}) or {}
        details = self._stripe_value(
            parent,
            "subscription_details",
            {},
        ) or {}
        return self._stripe_id(
            self._stripe_value(details, "subscription")
        )

    def _timestamp(
        self,
        value: int | float | None,
    ) -> datetime | None:
        if value is None:
            return None

        return datetime.fromtimestamp(
            value,
            tz=timezone.utc,
        ).replace(tzinfo=None)

    def _money(self, cents: int | None) -> Decimal:
        return (
            Decimal(int(cents or 0)) / Decimal("100")
        ).quantize(Decimal("0.01"))


    def _stripe_dict(self, value):
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if hasattr(value, "to_dict_recursive"):
            return value.to_dict_recursive()
        if hasattr(value, "to_dict"):
            return value.to_dict()
        try:
            return dict(value)
        except Exception:
            return {}
    def _serialize(self, value: Any) -> str:
        return json.dumps(
            value or {},
            ensure_ascii=False,
            default=str,
        )

    def _parse(self, value: str | None) -> dict:
        if not value:
            return {}

        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _response(
        self,
        invoice: BillingInvoice,
    ) -> BillingInvoiceResponse:
        return BillingInvoiceResponse(
            id=invoice.id,
            user_id=invoice.user_id,
            billing_customer_id=invoice.billing_customer_id,
            user_subscription_id=invoice.user_subscription_id,
            billing_payment_id=invoice.billing_payment_id,
            provider=invoice.provider,
            provider_invoice_id=invoice.provider_invoice_id,
            invoice_number=invoice.invoice_number,
            status=invoice.status,
            currency=invoice.currency,
            subtotal=invoice.subtotal,
            discount_amount=invoice.discount_amount,
            tax_amount=invoice.tax_amount,
            total=invoice.total,
            amount_paid=invoice.amount_paid,
            hosted_invoice_url=invoice.hosted_invoice_url,
            invoice_pdf_url=invoice.invoice_pdf_url,
            period_start=invoice.period_start,
            period_end=invoice.period_end,
            due_at=invoice.due_at,
            paid_at=invoice.paid_at,
            metadata=self._parse(invoice.metadata_json),
            created_at=invoice.created_at,
            updated_at=invoice.updated_at,
        )

    def list_invoices(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        status: BillingInvoiceStatus | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> BillingInvoiceListResponse:
        status_value = status.value if status else None

        invoices = billing_invoice_repository.list_all_filtered(
            db,
            user_id=user_id,
            status=status_value,
            skip=skip,
            limit=limit,
        )

        total = billing_invoice_repository.count_filtered(
            db,
            user_id=user_id,
            status=status_value,
        )

        return BillingInvoiceListResponse(
            items=[
                self._response(invoice)
                for invoice in invoices
            ],
            total=total,
            skip=skip,
            limit=limit,
        )

    def sync_invoice(
        self,
        db: Session,
        *,
        stripe_invoice: Any,
    ) -> BillingInvoice:
        provider_invoice_id = self._stripe_value(
            stripe_invoice,
            "id",
        )

        customer_id = self._stripe_value(
            stripe_invoice,
            "customer",
        )

        if not isinstance(customer_id, str):
            customer_id = self._stripe_value(
                customer_id,
                "id",
            )

        billing_customer = None

        if customer_id:
            billing_customer = (
                billing_customer_repository
                .get_by_provider_customer_id(
                    db,
                    provider=BillingProvider.STRIPE.value,
                    provider_customer_id=customer_id,
                )
            )

        subscription_id = self.provider_subscription_id(
            stripe_invoice
        )

        user_subscription = None

        if subscription_id:
            user_subscription = (
                user_subscription_repository
                .get_by_provider_subscription_id(
                    db,
                    provider_subscription_id=subscription_id,
                )
            )

        user_id = None

        if user_subscription:
            user_id = user_subscription.user_id
        elif billing_customer:
            user_id = billing_customer.user_id

        if user_id is None:
            raise ValueError(
                "Internal user could not be resolved for invoice."
            )

        payment_intent_id = self._stripe_value(
            stripe_invoice,
            "payment_intent",
        )

        if not isinstance(payment_intent_id, str):
            payment_intent_id = self._stripe_value(
                payment_intent_id,
                "id",
            )

        payment = None

        if payment_intent_id:
            payment = (
                billing_payment_repository
                .get_by_payment_intent_id(
                    db,
                    payment_intent_id,
                )
            )

        invoice_status = (
            self._stripe_value(
                stripe_invoice,
                "status",
                BillingInvoiceStatus.OPEN.value,
            )
            or BillingInvoiceStatus.OPEN.value
        )

        currency = (
            self._stripe_value(
                stripe_invoice,
                "currency",
                "usd",
            )
            or "usd"
        ).upper()

        amount_paid = self._money(
            self._stripe_value(
                stripe_invoice,
                "amount_paid",
                0,
            )
        )

        total = self._money(
            self._stripe_value(
                stripe_invoice,
                "total",
                0,
            )
        )

        if not payment and payment_intent_id:
            payment = BillingPayment(
                user_id=user_id,
                billing_customer_id=(
                    billing_customer.id
                    if billing_customer
                    else None
                ),
                user_subscription_id=(
                    user_subscription.id
                    if user_subscription
                    else None
                ),
                provider=BillingProvider.STRIPE.value,
                payment_type=BillingPaymentType.SUBSCRIPTION_RENEWAL.value,
                status=(
                    BillingPaymentStatus.SUCCEEDED.value
                    if invoice_status == BillingInvoiceStatus.PAID.value
                    else BillingPaymentStatus.PROCESSING.value
                ),
                currency=currency,
                amount=total,
                refunded_amount=Decimal("0.00"),
                provider_payment_intent_id=payment_intent_id,
                description=f"Stripe invoice {provider_invoice_id}",
                paid_at=(
                    utc_now()
                    if invoice_status == BillingInvoiceStatus.PAID.value
                    else None
                ),
            )

            db.add(payment)
            db.flush()

        elif payment:
            payment.amount = total
            payment.currency = currency

            if invoice_status == BillingInvoiceStatus.PAID.value:
                payment.status = BillingPaymentStatus.SUCCEEDED.value
                payment.paid_at = payment.paid_at or utc_now()

            db.add(payment)
            db.flush()

        values = {
            "user_id": user_id,
            "billing_customer_id": (
                billing_customer.id
                if billing_customer
                else None
            ),
            "user_subscription_id": (
                user_subscription.id
                if user_subscription
                else None
            ),
            "billing_payment_id": (
                payment.id
                if payment
                else None
            ),
            "provider": BillingProvider.STRIPE.value,
            "provider_invoice_id": provider_invoice_id,
            "invoice_number": self._stripe_value(
                stripe_invoice,
                "number",
            ),
            "status": invoice_status,
            "currency": currency,
            "subtotal": self._money(
                self._stripe_value(
                    stripe_invoice,
                    "subtotal",
                    0,
                )
            ),
            "discount_amount": self._money(
                self._stripe_value(
                    stripe_invoice,
                    "total_discount_amounts",
                    [],
                )[0].get("amount", 0)
                if self._stripe_value(
                    stripe_invoice,
                    "total_discount_amounts",
                    [],
                )
                else 0
            ),
            "tax_amount": self._money(
                self._stripe_value(
                    stripe_invoice,
                    "total_tax_amounts",
                    [],
                )[0].get("amount", 0)
                if self._stripe_value(
                    stripe_invoice,
                    "total_tax_amounts",
                    [],
                )
                else 0
            ),
            "total": total,
            "amount_paid": amount_paid,
            "hosted_invoice_url": self._stripe_value(
                stripe_invoice,
                "hosted_invoice_url",
            ),
            "invoice_pdf_url": self._stripe_value(
                stripe_invoice,
                "invoice_pdf",
            ),
            "period_start": self._timestamp(
                self._stripe_value(
                    stripe_invoice,
                    "period_start",
                )
            ),
            "period_end": self._timestamp(
                self._stripe_value(
                    stripe_invoice,
                    "period_end",
                )
            ),
            "due_at": self._timestamp(
                self._stripe_value(
                    stripe_invoice,
                    "due_date",
                )
            ),
            "paid_at": self._timestamp(
                self._stripe_value(
                    self._stripe_value(
                        stripe_invoice,
                        "status_transitions",
                        {},
                    ),
                    "paid_at",
                )
            ),
            "metadata_json": self._serialize(
                self._stripe_dict(
                    self._stripe_value(
                        stripe_invoice,
                        "metadata",
                        {},
                    )
                )
            ),
        }

        existing = (
            billing_invoice_repository
            .get_by_provider_invoice_id(
                db,
                provider_invoice_id,
            )
        )

        if existing:
            invoice = billing_invoice_repository.update(
                db,
                db_obj=existing,
                data=values,
            )
        else:
            invoice = billing_invoice_repository.create(
                db,
                data=values,
            )

        return invoice

    def mark_payment_failed(
        self,
        db: Session,
        *,
        stripe_invoice: Any,
    ) -> BillingInvoice:
        invoice = self.sync_invoice(
            db,
            stripe_invoice=stripe_invoice,
        )

        if invoice.billing_payment_id:
            payment = billing_payment_repository.get_by_id(
                db,
                invoice.billing_payment_id,
            )

            if payment:
                payment.status = BillingPaymentStatus.FAILED.value
                payment.failure_message = (
                    "Stripe invoice payment failed."
                )
                payment.failed_at = utc_now()

                db.add(payment)

        if invoice.user_subscription_id:
            subscription = (
                user_subscription_repository.get_by_id(
                    db,
                    invoice.user_subscription_id,
                )
            )

            if subscription:
                subscription.status = (
                    SubscriptionStatus.PAST_DUE.value
                )
                db.add(subscription)

        db.commit()
        db.refresh(invoice)

        return invoice


billing_invoice_service = BillingInvoiceService()