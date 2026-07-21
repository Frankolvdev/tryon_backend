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
from app.models.subscription_plan import SubscriptionPlan
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
from app.services.billing_payment_method_service import (
    billing_payment_method_service,
)
from app.services.stripe_client_service import stripe_client_service


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

    def provider_subscription_id(
        self,
        stripe_invoice: Any,
    ) -> str | None:
        direct = self._stripe_id(
            self._stripe_value(stripe_invoice, "subscription")
        )
        if direct:
            return direct

        parent = (
            self._stripe_value(stripe_invoice, "parent", {})
            or {}
        )
        details = (
            self._stripe_value(
                parent,
                "subscription_details",
                {},
            )
            or {}
        )
        return self._stripe_id(
            self._stripe_value(details, "subscription")
        )

    def payment_intent_id(
        self,
        stripe_invoice: Any,
    ) -> str | None:
        direct = self._stripe_id(
            self._stripe_value(
                stripe_invoice,
                "payment_intent",
            )
        )
        if direct:
            return direct

        payments = (
            self._stripe_value(stripe_invoice, "payments", {})
            or {}
        )
        data = self._stripe_value(payments, "data", []) or []
        for item in data:
            payment_ref = (
                self._stripe_value(item, "payment", {})
                or {}
            )
            payment_type = self._stripe_value(
                payment_ref,
                "type",
            )
            if payment_type not in {None, "payment_intent"}:
                continue

            payment_intent = self._stripe_id(
                self._stripe_value(
                    payment_ref,
                    "payment_intent",
                )
            )
            if payment_intent:
                return payment_intent
        return None

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

    def _stripe_dict(
        self,
        value: Any,
    ) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value

        to_dict_recursive = getattr(
            value,
            "to_dict_recursive",
            None,
        )
        if callable(to_dict_recursive):
            converted = to_dict_recursive()
            return converted if isinstance(converted, dict) else {}

        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            converted = to_dict()
            return converted if isinstance(converted, dict) else {}

        try:
            converted = dict(value)
        except (TypeError, ValueError, KeyError):
            return {}
        return converted if isinstance(converted, dict) else {}

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
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

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

    def _resolve_payment_from_metadata(
        self,
        db: Session,
        metadata: dict[str, Any],
    ) -> BillingPayment | None:
        raw_payment_id = metadata.get("billing_payment_id")
        if raw_payment_id is None:
            return None
        try:
            payment_id = int(raw_payment_id)
        except (TypeError, ValueError):
            return None
        return billing_payment_repository.get_by_id(
            db,
            payment_id,
        )

    def _payment_type(
        self,
        *,
        payment: BillingPayment | None,
        metadata: dict[str, Any],
        billing_reason: str | None,
    ) -> str:
        if payment:
            return payment.payment_type

        if metadata.get("type") == "token_purchase":
            return BillingPaymentType.TOKEN_PURCHASE.value

        if billing_reason == "subscription_create":
            return BillingPaymentType.SUBSCRIPTION.value
        return BillingPaymentType.SUBSCRIPTION_RENEWAL.value

    def _payment_description(
        self,
        db: Session,
        *,
        payment_type: str,
        user_subscription: Any,
        metadata: dict[str, Any],
        billing_reason: str | None,
    ) -> str:
        if payment_type == BillingPaymentType.TOKEN_PURCHASE.value:
            purchase_kind = metadata.get("purchase_kind")
            if purchase_kind == "package":
                return "Compra de paquete de tokens"
            return "Compra directa de tokens"

        plan_name = "Plan de suscripción"
        if user_subscription:
            plan = db.get(
                SubscriptionPlan,
                user_subscription.subscription_plan_id,
            )
            if plan:
                plan_name = plan.name

        if billing_reason == "subscription_create":
            return f"Suscripción a {plan_name}"
        return f"Renovación de {plan_name}"

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

        invoice_metadata = self._stripe_dict(
            self._stripe_value(
                stripe_invoice,
                "metadata",
                {},
            )
        )
        payment_intent_id = self.payment_intent_id(
            stripe_invoice
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
        if not payment:
            payment = self._resolve_payment_from_metadata(
                db,
                invoice_metadata,
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
        billing_reason = self._stripe_value(
            stripe_invoice,
            "billing_reason",
        )

        payment_type = self._payment_type(
            payment=payment,
            metadata=invoice_metadata,
            billing_reason=billing_reason,
        )
        description = self._payment_description(
            db,
            payment_type=payment_type,
            user_subscription=user_subscription,
            metadata=invoice_metadata,
            billing_reason=billing_reason,
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
                payment_type=payment_type,
                status=(
                    BillingPaymentStatus.SUCCEEDED.value
                    if invoice_status
                    == BillingInvoiceStatus.PAID.value
                    else BillingPaymentStatus.PROCESSING.value
                ),
                currency=currency,
                amount=total,
                refunded_amount=Decimal("0.00"),
                provider_payment_intent_id=payment_intent_id,
                description=description,
                metadata_json=self._serialize(
                    invoice_metadata
                ),
                paid_at=(
                    utc_now()
                    if invoice_status
                    == BillingInvoiceStatus.PAID.value
                    else None
                ),
            )
            db.add(payment)
            db.flush()
        elif payment:
            payment.amount = total
            payment.currency = currency
            payment.description = description
            payment.metadata_json = self._serialize(
                {
                    **self._parse(payment.metadata_json),
                    **invoice_metadata,
                }
            )
            if invoice_status == BillingInvoiceStatus.PAID.value:
                payment.status = (
                    BillingPaymentStatus.SUCCEEDED.value
                )
                payment.paid_at = payment.paid_at or utc_now()
            db.add(payment)
            db.flush()

        if payment and payment_intent_id:
            try:
                payment_intent = (
                    stripe_client_service.retrieve_payment_intent(
                        db,
                        payment_intent_id=payment_intent_id,
                    )
                )
                billing_payment_method_service.apply_from_payment_intent(
                    db,
                    payment=payment,
                    payment_intent=payment_intent,
                    retrieve_if_needed=False,
                )
                db.add(payment)
                db.flush()
            except Exception:
                # Invoice synchronization must not fail only because
                # optional presentation details could not be hydrated.
                pass

        discount_amounts = (
            self._stripe_value(
                stripe_invoice,
                "total_discount_amounts",
                [],
            )
            or []
        )
        tax_amounts = (
            self._stripe_value(
                stripe_invoice,
                "total_tax_amounts",
                [],
            )
            or []
        )

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
                payment.id if payment else None
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
                    discount_amounts[0],
                    "amount",
                    0,
                )
                if discount_amounts
                else 0
            ),
            "tax_amount": self._money(
                self._stripe_value(
                    tax_amounts[0],
                    "amount",
                    0,
                )
                if tax_amounts
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
                invoice_metadata
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
            return billing_invoice_repository.update(
                db,
                db_obj=existing,
                data=values,
            )
        return billing_invoice_repository.create(
            db,
            data=values,
        )

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
                payment.status = (
                    BillingPaymentStatus.FAILED.value
                )
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
