from typing import Any

from sqlalchemy.orm import Session

from app.common.billing_enums import (
    BillingInvoiceStatus,
    BillingPaymentStatus,
    TokenPurchaseStatus,
)
from app.common.time import utc_now
from app.repositories.billing_payment_repository import (
    billing_payment_repository,
)
from app.repositories.token_purchase_repository import (
    token_purchase_repository,
)
from app.schemas.stripe_billing import StripeWebhookResult
from app.schemas.token_purchase import (
    TokenPurchaseCheckoutRequest,
    TokenPurchaseCheckoutResponse,
)
from app.services.billing_invoice_service import (
    billing_invoice_service,
)
from app.services.subscription_service import (
    subscription_service,
)
from app.services.token_purchase_service import (
    token_purchase_service,
)


class BillingService:
    def _value(
        self,
        obj: Any,
        key: str,
        default: Any = None,
    ) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)

        return getattr(
            obj,
            key,
            default,
        )

    def create_token_checkout(
        self,
        db: Session,
        *,
        user,
        data: TokenPurchaseCheckoutRequest,
    ) -> TokenPurchaseCheckoutResponse:
        return token_purchase_service.create_checkout(
            db,
            user=user,
            data=data,
        )

    def handle_verified_stripe_event(
        self,
        db: Session,
        *,
        event: Any,
    ) -> StripeWebhookResult:
        event_type = self._value(
            event,
            "type",
        )

        event_id = self._value(
            event,
            "id",
        )

        data = self._value(
            event,
            "data",
            {},
        )

        event_object = self._value(
            data,
            "object",
            {},
        )

        handlers = {
            "checkout.session.completed": (
                self._checkout_completed
            ),
            "checkout.session.async_payment_succeeded": (
                self._checkout_completed
            ),
            "checkout.session.expired": (
                self._checkout_failed
            ),
            "checkout.session.async_payment_failed": (
                self._checkout_failed
            ),
            "payment_intent.succeeded": (
                self._payment_intent_succeeded
            ),
            "payment_intent.payment_failed": (
                self._payment_intent_failed
            ),
            "customer.subscription.created": (
                self._subscription_changed
            ),
            "customer.subscription.updated": (
                self._subscription_changed
            ),
            "customer.subscription.deleted": (
                self._subscription_changed
            ),
            "invoice.paid": (
                self._invoice_paid
            ),
            "invoice.payment_failed": (
                self._invoice_payment_failed
            ),
            "invoice.voided": (
                self._invoice_changed
            ),
            "invoice.marked_uncollectible": (
                self._invoice_changed
            ),
            "refund.created": (
                self._refund_changed
            ),
            "refund.updated": (
                self._refund_changed
            ),
            "refund.failed": (
                self._refund_changed
            ),
            "charge.refunded": (
                self._charge_refunded
            ),
        }

        handler = handlers.get(
            event_type,
        )

        if not handler:
            return StripeWebhookResult(
                received=True,
                event_type=event_type,
                message=(
                    "Stripe event received and stored, "
                    "but no business action was required."
                ),
                metadata={
                    "stripe_event_id": event_id,
                    "ignored": True,
                },
            )

        return handler(
            db,
            event_type=event_type,
            event_id=event_id,
            event_object=event_object,
        )

    def _checkout_completed(
        self,
        db: Session,
        *,
        event_type: str,
        event_id: str,
        event_object: Any,
    ) -> StripeWebhookResult:
        metadata = self._value(
            event_object,
            "metadata",
            {},
        ) or {}

        checkout_type = self._value(
            metadata,
            "type",
        )

        if checkout_type == "token_purchase":
            purchase = (
                token_purchase_service
                .process_checkout_completed(
                    db,
                    checkout_session=event_object,
                )
            )

            return StripeWebhookResult(
                received=True,
                event_type=event_type,
                message=(
                    "Token purchase was processed "
                    "idempotently."
                ),
                metadata={
                    "stripe_event_id": event_id,
                    "token_purchase_id": purchase.id,
                    "purchase_status": purchase.status,
                },
            )

        if checkout_type == "subscription_checkout":
            return StripeWebhookResult(
                received=True,
                event_type=event_type,
                message=(
                    "Subscription Checkout completed. "
                    "Subscription state will be synchronized "
                    "from its subscription webhook."
                ),
                metadata={
                    "stripe_event_id": event_id,
                    "checkout_session_id": self._value(
                        event_object,
                        "id",
                    ),
                },
            )

        return StripeWebhookResult(
            received=True,
            event_type=event_type,
            message=(
                "Unsupported Checkout type ignored."
            ),
            metadata={
                "stripe_event_id": event_id,
                "checkout_type": checkout_type,
            },
        )

    def _checkout_failed(
        self,
        db: Session,
        *,
        event_type: str,
        event_id: str,
        event_object: Any,
    ) -> StripeWebhookResult:
        purchase = (
            token_purchase_service
            .mark_checkout_failed(
                db,
                checkout_session=event_object,
                error_message=event_type,
            )
        )

        return StripeWebhookResult(
            received=True,
            event_type=event_type,
            message=(
                "Failed Checkout Session processed."
            ),
            metadata={
                "stripe_event_id": event_id,
                "token_purchase_id": (
                    purchase.id
                    if purchase
                    else None
                ),
            },
        )

    def _subscription_changed(
        self,
        db: Session,
        *,
        event_type: str,
        event_id: str,
        event_object: Any,
    ) -> StripeWebhookResult:
        subscription = (
            subscription_service
            .sync_from_stripe_object(
                db,
                stripe_subscription=event_object,
            )
        )

        return StripeWebhookResult(
            received=True,
            event_type=event_type,
            message=(
                "Subscription synchronized."
            ),
            metadata={
                "stripe_event_id": event_id,
                "user_subscription_id": (
                    subscription.id
                ),
                "status": subscription.status,
            },
        )

    def _invoice_paid(
        self,
        db: Session,
        *,
        event_type: str,
        event_id: str,
        event_object: Any,
    ) -> StripeWebhookResult:
        invoice = (
            billing_invoice_service
            .sync_invoice(
                db,
                stripe_invoice=event_object,
            )
        )

        subscription = None

        if not invoice.user_subscription_id:
            provider_subscription_id = (
                billing_invoice_service.provider_subscription_id(
                    event_object
                )
            )

            if provider_subscription_id:
                stripe_subscription = (
                    subscription_service
                    .retrieve_and_sync_provider_subscription(
                        db,
                        provider_subscription_id=(
                            provider_subscription_id
                        ),
                    )
                )
                invoice = billing_invoice_service.sync_invoice(
                    db,
                    stripe_invoice=event_object,
                )

        if invoice.user_subscription_id:
            subscription = (
                subscription_service
                .grant_period_tokens_if_needed(
                    db,
                    subscription_id=invoice.user_subscription_id,
                    reference_id=invoice.provider_invoice_id,
                )
            )

        return StripeWebhookResult(
            received=True,
            event_type=event_type,
            message=(
                "Paid invoice synchronized and subscription "
                "tokens granted idempotently."
            ),
            metadata={
                "stripe_event_id": event_id,
                "billing_invoice_id": invoice.id,
                "user_subscription_id": (
                    subscription.id
                    if subscription
                    else None
                ),
            },
        )

    def _invoice_payment_failed(
        self,
        db: Session,
        *,
        event_type: str,
        event_id: str,
        event_object: Any,
    ) -> StripeWebhookResult:
        invoice = (
            billing_invoice_service
            .mark_payment_failed(
                db,
                stripe_invoice=event_object,
            )
        )

        return StripeWebhookResult(
            received=True,
            event_type=event_type,
            message=(
                "Failed invoice payment recorded."
            ),
            metadata={
                "stripe_event_id": event_id,
                "billing_invoice_id": invoice.id,
            },
        )

    def _invoice_changed(
        self,
        db: Session,
        *,
        event_type: str,
        event_id: str,
        event_object: Any,
    ) -> StripeWebhookResult:
        invoice = (
            billing_invoice_service
            .sync_invoice(
                db,
                stripe_invoice=event_object,
            )
        )

        return StripeWebhookResult(
            received=True,
            event_type=event_type,
            message=(
                "Invoice synchronized."
            ),
            metadata={
                "stripe_event_id": event_id,
                "billing_invoice_id": invoice.id,
                "status": invoice.status,
            },
        )

    def _payment_intent_succeeded(
        self,
        db: Session,
        *,
        event_type: str,
        event_id: str,
        event_object: Any,
    ) -> StripeWebhookResult:
        payment_intent_id = self._value(
            event_object,
            "id",
        )

        payment = (
            billing_payment_repository
            .get_by_payment_intent_id(
                db,
                payment_intent_id,
            )
        )

        if payment:
            payment.status = (
                BillingPaymentStatus.SUCCEEDED.value
            )

            payment.paid_at = (
                payment.paid_at
                or utc_now()
            )

            latest_charge = self._value(
                event_object,
                "latest_charge",
            )

            if isinstance(
                latest_charge,
                str,
            ):
                payment.provider_charge_id = (
                    latest_charge
                )
            else:
                payment.provider_charge_id = (
                    self._value(
                        latest_charge,
                        "id",
                    )
                )

            db.add(payment)
            db.commit()

        return StripeWebhookResult(
            received=True,
            event_type=event_type,
            message=(
                "PaymentIntent success synchronized."
            ),
            metadata={
                "stripe_event_id": event_id,
                "billing_payment_id": (
                    payment.id
                    if payment
                    else None
                ),
            },
        )

    def _payment_intent_failed(
        self,
        db: Session,
        *,
        event_type: str,
        event_id: str,
        event_object: Any,
    ) -> StripeWebhookResult:
        payment_intent_id = self._value(
            event_object,
            "id",
        )

        payment = (
            billing_payment_repository
            .get_by_payment_intent_id(
                db,
                payment_intent_id,
            )
        )

        if payment:
            last_error = self._value(
                event_object,
                "last_payment_error",
                {},
            ) or {}

            payment.status = (
                BillingPaymentStatus.FAILED.value
            )

            payment.failure_code = self._value(
                last_error,
                "code",
            )

            payment.failure_message = self._value(
                last_error,
                "message",
            )

            payment.failed_at = utc_now()

            db.add(payment)
            db.commit()

        return StripeWebhookResult(
            received=True,
            event_type=event_type,
            message=(
                "PaymentIntent failure synchronized."
            ),
            metadata={
                "stripe_event_id": event_id,
                "billing_payment_id": (
                    payment.id
                    if payment
                    else None
                ),
            },
        )

    def _refund_changed(
        self,
        db: Session,
        *,
        event_type: str,
        event_id: str,
        event_object: Any,
    ) -> StripeWebhookResult:
        payment_intent_id = self._value(
            event_object,
            "payment_intent",
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

        return StripeWebhookResult(
            received=True,
            event_type=event_type,
            message="Refund event recorded.",
            metadata={
                "stripe_event_id": event_id,
                "stripe_refund_id": self._value(
                    event_object,
                    "id",
                ),
                "billing_payment_id": (
                    payment.id
                    if payment
                    else None
                ),
            },
        )

    def _charge_refunded(
        self,
        db: Session,
        *,
        event_type: str,
        event_id: str,
        event_object: Any,
    ) -> StripeWebhookResult:
        payment_intent_id = self._value(
            event_object,
            "payment_intent",
        )

        payment = None
        purchase = None

        if payment_intent_id:
            payment = (
                billing_payment_repository
                .get_by_payment_intent_id(
                    db,
                    payment_intent_id,
                )
            )

            purchase = (
                token_purchase_repository
                .get_by_payment_intent_id(
                    db,
                    payment_intent_id,
                )
            )

        amount_refunded = self._value(
            event_object,
            "amount_refunded",
            0,
        )

        amount_total = self._value(
            event_object,
            "amount",
            0,
        )

        fully_refunded = (
            amount_total > 0
            and amount_refunded >= amount_total
        )

        if payment:
            from decimal import Decimal

            payment.refunded_amount = (
                Decimal(amount_refunded)
                / Decimal("100")
            ).quantize(
                Decimal("0.01")
            )

            payment.refunded_at = utc_now()

            payment.status = (
                BillingPaymentStatus.REFUNDED.value
                if fully_refunded
                else BillingPaymentStatus.PARTIALLY_REFUNDED.value
            )

            db.add(payment)

        if purchase and fully_refunded:
            purchase.status = (
                TokenPurchaseStatus.REFUNDED.value
            )

            purchase.refunded_at = utc_now()

            db.add(purchase)

        db.commit()

        return StripeWebhookResult(
            received=True,
            event_type=event_type,
            message=(
                "Charge refund synchronized."
            ),
            metadata={
                "stripe_event_id": event_id,
                "billing_payment_id": (
                    payment.id
                    if payment
                    else None
                ),
                "token_purchase_id": (
                    purchase.id
                    if purchase
                    else None
                ),
                "fully_refunded": fully_refunded,
            },
        )


billing_service = BillingService()