import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from app.common.billing_enums import (
    BillingInvoiceStatus,
    BillingPaymentStatus,
    BillingPaymentType,
)
from app.common.exceptions import (
    ConflictException,
    NotFoundException,
)
from app.common.time import utc_now
from app.models.billing_invoice import BillingInvoice
from app.models.billing_payment import BillingPayment
from app.repositories.billing_invoice_repository import (
    billing_invoice_repository,
)
from app.repositories.billing_payment_repository import (
    billing_payment_repository,
)
from app.schemas.billing_history import (
    BillingInvoiceDocumentResponse,
    BillingInvoiceHistoryListResponse,
    BillingInvoiceHistoryResponse,
    BillingPaymentHistoryListResponse,
    BillingPaymentHistoryResponse,
    BillingPaymentReconcileResponse,
    BillingPaymentRefundRequest,
    BillingPaymentRefundResponse,
)
from app.services.billing_invoice_policy_service import (
    billing_invoice_policy_service,
)
from app.services.billing_payment_method_service import (
    billing_payment_method_service,
)
from app.services.integration_service import integration_service
from app.services.stripe_client_service import stripe_client_service


class BillingHistoryService:
    def _serialize(self, value: Any) -> str:
        return json.dumps(
            value or {},
            ensure_ascii=False,
            default=str,
        )

    def _parse(
        self,
        value: str | None,
    ) -> dict[str, Any]:
        if not value:
            return {}
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _stripe_value(
        self,
        obj: Any,
        key: str,
        default: Any = None,
    ) -> Any:
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _money_to_cents(
        self,
        amount: Decimal,
    ) -> int:
        normalized = amount.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        return int(normalized * Decimal("100"))

    def _cents_to_money(
        self,
        amount: int | None,
    ) -> Decimal:
        return (
            Decimal(int(amount or 0)) / Decimal("100")
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    def _payment_response(
        self,
        payment: BillingPayment,
    ) -> BillingPaymentHistoryResponse:
        refunded_amount = (
            payment.refunded_amount
            or Decimal("0.00")
        )
        refundable_amount = (
            payment.amount - refunded_amount
        )
        if refundable_amount < Decimal("0.00"):
            refundable_amount = Decimal("0.00")

        payment_method = (
            billing_payment_method_service
            .details_from_payment(payment)
        )
        return BillingPaymentHistoryResponse(
            id=payment.id,
            user_id=payment.user_id,
            billing_customer_id=payment.billing_customer_id,
            user_subscription_id=payment.user_subscription_id,
            provider=payment.provider,
            payment_type=payment.payment_type,
            status=payment.status,
            currency=payment.currency,
            amount=payment.amount,
            refunded_amount=refunded_amount,
            refundable_amount=refundable_amount,
            provider_payment_intent_id=(
                payment.provider_payment_intent_id
            ),
            provider_charge_id=payment.provider_charge_id,
            provider_checkout_session_id=(
                payment.provider_checkout_session_id
            ),
            failure_code=payment.failure_code,
            failure_message=payment.failure_message,
            description=payment.description,
            payment_method_type=payment_method[
                "payment_method_type"
            ],
            payment_method_brand=payment_method[
                "payment_method_brand"
            ],
            payment_method_last4=payment_method[
                "payment_method_last4"
            ],
            payment_method_wallet=payment_method[
                "payment_method_wallet"
            ],
            metadata=self._parse(payment.metadata_json),
            paid_at=payment.paid_at,
            failed_at=payment.failed_at,
            refunded_at=payment.refunded_at,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
        )

    def _invoice_response(
        self,
        db: Session,
        invoice: BillingInvoice,
    ) -> BillingInvoiceHistoryResponse:
        documents_enabled = (
            billing_invoice_policy_service
            .invoice_documents_enabled(
                db,
                invoice,
            )
        )
        return BillingInvoiceHistoryResponse(
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
            hosted_invoice_url=(
                invoice.hosted_invoice_url
                if documents_enabled
                else None
            ),
            invoice_pdf_url=(
                invoice.invoice_pdf_url
                if documents_enabled
                else None
            ),
            invoice_documents_enabled=documents_enabled,
            period_start=invoice.period_start,
            period_end=invoice.period_end,
            due_at=invoice.due_at,
            paid_at=invoice.paid_at,
            metadata=self._parse(invoice.metadata_json),
            created_at=invoice.created_at,
            updated_at=invoice.updated_at,
        )

    def get_payment(
        self,
        db: Session,
        *,
        payment_id: int,
        user_id: int | None = None,
    ) -> BillingPayment:
        payment = billing_payment_repository.get_by_id(
            db,
            payment_id,
        )
        if not payment:
            raise NotFoundException(
                "Billing payment not found."
            )
        if (
            user_id is not None
            and payment.user_id != user_id
        ):
            raise NotFoundException(
                "Billing payment not found."
            )
        return payment

    def get_invoice(
        self,
        db: Session,
        *,
        invoice_id: int,
        user_id: int | None = None,
    ) -> BillingInvoice:
        invoice = billing_invoice_repository.get_by_id(
            db,
            invoice_id,
        )
        if not invoice:
            raise NotFoundException(
                "Billing invoice not found."
            )
        if (
            user_id is not None
            and invoice.user_id != user_id
        ):
            raise NotFoundException(
                "Billing invoice not found."
            )
        return invoice

    def get_payment_response(
        self,
        db: Session,
        *,
        payment_id: int,
        user_id: int | None = None,
    ) -> BillingPaymentHistoryResponse:
        payment = self.get_payment(
            db,
            payment_id=payment_id,
            user_id=user_id,
        )
        return self._payment_response(payment)

    def get_invoice_response(
        self,
        db: Session,
        *,
        invoice_id: int,
        user_id: int | None = None,
    ) -> BillingInvoiceHistoryResponse:
        invoice = self.get_invoice(
            db,
            invoice_id=invoice_id,
            user_id=user_id,
        )
        return self._invoice_response(db, invoice)

    def list_payments(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        status: BillingPaymentStatus | None = None,
        payment_type: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> BillingPaymentHistoryListResponse:
        status_value = status.value if status else None
        payments = (
            billing_payment_repository
            .list_all_filtered(
                db,
                user_id=user_id,
                status=status_value,
                payment_type=payment_type,
                skip=skip,
                limit=limit,
            )
        )
        total = (
            billing_payment_repository
            .count_filtered(
                db,
                user_id=user_id,
                status=status_value,
                payment_type=payment_type,
            )
        )
        hydrated_any = False
        for payment in payments:
            if (
                payment.provider_payment_intent_id
                and not billing_payment_method_service.is_hydrated(payment)
            ):
                try:
                    payment_intent = (
                        stripe_client_service.retrieve_payment_intent(
                            db,
                            payment_intent_id=(
                                payment.provider_payment_intent_id
                            ),
                        )
                    )
                    billing_payment_method_service.apply_from_payment_intent(
                        db,
                        payment=payment,
                        payment_intent=payment_intent,
                        retrieve_if_needed=False,
                    )
                    db.add(payment)
                    hydrated_any = True
                except Exception:
                    # Historical presentation enrichment must never block
                    # access to the payment history.
                    continue

        if hydrated_any:
            db.commit()

        return BillingPaymentHistoryListResponse(
            items=[
                self._payment_response(payment)
                for payment in payments
            ],
            total=total,
            skip=skip,
            limit=limit,
        )

    def list_invoices(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        status: BillingInvoiceStatus | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> BillingInvoiceHistoryListResponse:
        status_value = status.value if status else None
        invoices = (
            billing_invoice_repository
            .list_all_filtered(
                db,
                user_id=user_id,
                status=status_value,
                skip=skip,
                limit=limit,
            )
        )
        total = (
            billing_invoice_repository
            .count_filtered(
                db,
                user_id=user_id,
                status=status_value,
            )
        )
        return BillingInvoiceHistoryListResponse(
            items=[
                self._invoice_response(db, invoice)
                for invoice in invoices
            ],
            total=total,
            skip=skip,
            limit=limit,
        )

    def get_invoice_documents(
        self,
        db: Session,
        *,
        invoice_id: int,
        user_id: int | None = None,
    ) -> BillingInvoiceDocumentResponse:
        invoice = self.get_invoice(
            db,
            invoice_id=invoice_id,
            user_id=user_id,
        )
        documents_enabled = (
            billing_invoice_policy_service
            .invoice_documents_enabled(
                db,
                invoice,
            )
        )
        if not documents_enabled:
            return BillingInvoiceDocumentResponse(
                invoice_id=invoice.id,
                hosted_invoice_url=None,
                invoice_pdf_url=None,
                available=False,
                message=(
                    "Invoice documents are disabled "
                    "for this purchase category."
                ),
            )

        available = bool(
            invoice.hosted_invoice_url
            or invoice.invoice_pdf_url
        )
        return BillingInvoiceDocumentResponse(
            invoice_id=invoice.id,
            hosted_invoice_url=invoice.hosted_invoice_url,
            invoice_pdf_url=invoice.invoice_pdf_url,
            available=available,
            message=(
                "Invoice documents are available."
                if available
                else "Invoice documents are not available yet."
            ),
        )

    def reconcile_payment(
        self,
        db: Session,
        *,
        payment_id: int,
    ) -> BillingPaymentReconcileResponse:
        payment = self.get_payment(
            db,
            payment_id=payment_id,
        )
        if not payment.provider_payment_intent_id:
            raise ConflictException(
                "Payment has no Stripe PaymentIntent."
            )

        payment_intent = (
            stripe_client_service.retrieve_payment_intent(
                db,
                payment_intent_id=(
                    payment.provider_payment_intent_id
                ),
            )
        )
        stripe_status = self._stripe_value(
            payment_intent,
            "status",
        )
        billing_payment_method_service.apply_from_payment_intent(
            db,
            payment=payment,
            payment_intent=payment_intent,
            retrieve_if_needed=False,
        )

        if stripe_status == "succeeded":
            payment.status = (
                BillingPaymentStatus.SUCCEEDED.value
            )
            payment.paid_at = payment.paid_at or utc_now()
            payment.failure_code = None
            payment.failure_message = None
        elif stripe_status in {
            "processing",
            "requires_action",
            "requires_confirmation",
        }:
            payment.status = (
                BillingPaymentStatus.PROCESSING.value
            )
        elif stripe_status == "requires_payment_method":
            payment.status = (
                BillingPaymentStatus.FAILED.value
            )
            last_payment_error = (
                self._stripe_value(
                    payment_intent,
                    "last_payment_error",
                    {},
                )
                or {}
            )
            payment.failure_code = self._stripe_value(
                last_payment_error,
                "code",
            )
            payment.failure_message = self._stripe_value(
                last_payment_error,
                "message",
            )
            payment.failed_at = utc_now()
        elif stripe_status == "canceled":
            payment.status = (
                BillingPaymentStatus.CANCELED.value
            )

        amount_received = self._stripe_value(
            payment_intent,
            "amount_received",
        )
        if amount_received is not None:
            payment.amount = self._cents_to_money(
                amount_received
            )

        payment.metadata_json = self._serialize(
            {
                **self._parse(payment.metadata_json),
                "last_reconciled_stripe_status": stripe_status,
                "last_reconciled_at": utc_now().isoformat(),
            }
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)

        integration_service.record_event(
            db,
            provider="stripe",
            event_type="billing_payment.reconciled",
            entity_type="billing_payment",
            entity_id=str(payment.id),
            payload={
                "payment_intent_id": (
                    payment.provider_payment_intent_id
                ),
            },
            response={
                "stripe_status": stripe_status,
                "internal_status": payment.status,
            },
        )
        return BillingPaymentReconcileResponse(
            payment=self._payment_response(payment),
            reconciled=True,
            message="Payment synchronized with Stripe.",
        )

    def refund_payment(
        self,
        db: Session,
        *,
        payment_id: int,
        data: BillingPaymentRefundRequest,
    ) -> BillingPaymentRefundResponse:
        payment = billing_payment_repository.get_for_update(
            db,
            payment_id,
        )
        if not payment:
            raise NotFoundException(
                "Billing payment not found."
            )

        if (
            payment.payment_type
            == BillingPaymentType.TOKEN_PURCHASE.value
        ):
            db.rollback()
            raise ConflictException(
                "Token purchases must be refunded "
                "through the token purchase refund endpoint."
            )

        if not payment.provider_payment_intent_id:
            db.rollback()
            raise ConflictException(
                "Payment has no Stripe PaymentIntent."
            )

        if payment.status not in {
            BillingPaymentStatus.SUCCEEDED.value,
            BillingPaymentStatus.PARTIALLY_REFUNDED.value,
        }:
            db.rollback()
            raise ConflictException(
                "Payment cannot be refunded "
                "in its current state."
            )

        previous_refunded_amount = (
            payment.refunded_amount
            or Decimal("0.00")
        )
        remaining_refundable = (
            payment.amount - previous_refunded_amount
        )
        if remaining_refundable <= Decimal("0.00"):
            db.rollback()
            raise ConflictException(
                "Payment has no refundable balance."
            )

        refund_amount = (
            data.amount
            if data.amount is not None
            else remaining_refundable
        )
        refund_amount = refund_amount.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        if refund_amount > remaining_refundable:
            db.rollback()
            raise ConflictException(
                "Refund amount exceeds the "
                "remaining refundable amount."
            )

        stripe_refund = (
            stripe_client_service.refund_payment_intent(
                db,
                payment_intent_id=(
                    payment.provider_payment_intent_id
                ),
                amount_cents=self._money_to_cents(
                    refund_amount
                ),
                reason=data.reason,
                metadata={
                    "billing_payment_id": str(payment.id),
                    "internal_user_id": str(payment.user_id),
                },
                idempotency_key=(
                    "billing-payment-refund-"
                    f"{payment.id}-"
                    f"{self._money_to_cents(refund_amount)}-"
                    f"{self._money_to_cents(previous_refunded_amount)}"
                ),
            )
        )
        stripe_refund_id = self._stripe_value(
            stripe_refund,
            "id",
        )
        if not stripe_refund_id:
            db.rollback()
            raise ConflictException(
                "Stripe did not return a refund ID."
            )

        new_refunded_amount = (
            previous_refunded_amount + refund_amount
        )
        fully_refunded = (
            new_refunded_amount >= payment.amount
        )
        payment.refunded_amount = new_refunded_amount
        payment.refunded_at = utc_now()
        payment.status = (
            BillingPaymentStatus.REFUNDED.value
            if fully_refunded
            else BillingPaymentStatus.PARTIALLY_REFUNDED.value
        )
        payment.metadata_json = self._serialize(
            {
                **self._parse(payment.metadata_json),
                "last_refund_id": stripe_refund_id,
                "last_refund_amount": str(refund_amount),
                "last_refund_reason": data.reason,
            }
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)

        integration_service.record_event(
            db,
            provider="stripe",
            event_type="billing_payment.refunded",
            entity_type="billing_payment",
            entity_id=str(payment.id),
            payload={
                "refund_amount": str(refund_amount),
                "reason": data.reason,
            },
            response={
                "stripe_refund_id": stripe_refund_id,
                "fully_refunded": fully_refunded,
                "total_refunded_amount": str(
                    payment.refunded_amount
                ),
            },
        )
        return BillingPaymentRefundResponse(
            payment=self._payment_response(payment),
            stripe_refund_id=str(stripe_refund_id),
            refunded_amount=refund_amount,
            fully_refunded=fully_refunded,
            message="Payment refunded successfully.",
        )


billing_history_service = BillingHistoryService()
