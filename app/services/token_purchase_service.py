import json
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from app.common.billing_enums import (
    BillingPaymentStatus,
    BillingPaymentType,
    BillingProvider,
    TokenPurchaseStatus,
)
from app.common.exceptions import (
    ConflictException,
    NotFoundException,
)
from app.common.time import utc_now
from app.models.billing_payment import BillingPayment
from app.models.token_purchase import TokenPurchase
from app.models.user import User
from app.repositories.billing_customer_repository import (
    billing_customer_repository,
)
from app.repositories.billing_payment_repository import (
    billing_payment_repository,
)
from app.repositories.token_package_repository import (
    token_package_repository,
)
from app.repositories.token_purchase_repository import (
    token_purchase_repository,
)
from app.schemas.token_purchase import (
    BillingPaymentResponse,
    TokenPurchaseCheckoutRequest,
    TokenPurchaseCheckoutResponse,
    TokenPurchaseDetailResponse,
    TokenPurchaseListResponse,
    TokenPurchaseReconcileResponse,
    TokenPurchaseRefundRequest,
    TokenPurchaseRefundResponse,
    TokenPurchaseResponse,
)
from app.services.billing_customer_service import (
    billing_customer_service,
)
from app.services.integration_service import integration_service
from app.services.stripe_client_service import (
    stripe_client_service,
)
from app.services.token_service import token_service


class TokenPurchaseService:
    def _serialize_json(self, value: Any) -> str:
        return json.dumps(
            value or {},
            ensure_ascii=False,
            default=str,
        )

    def _parse_json(self, value: str | None) -> dict[str, Any]:
        if not value:
            return {}

        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _stripe_value(
        self,
        obj: Any,
        key: str,
        default: Any = None,
    ) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)

        return getattr(obj, key, default)

    def _stripe_int(
        self,
        obj: Any,
        key: str,
    ) -> int | None:
        value = self._stripe_value(obj, key)

        if value in (None, ""):
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _money_to_cents(self, amount: Decimal) -> int:
        normalized = amount.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        return int(normalized * 100)

    def _cents_to_money(self, amount: int | None) -> Decimal:
        return (
            Decimal(int(amount or 0)) / Decimal("100")
        ).quantize(Decimal("0.01"))

    def _purchase_response(
        self,
        purchase: TokenPurchase,
    ) -> TokenPurchaseResponse:
        return TokenPurchaseResponse(
            id=purchase.id,
            user_id=purchase.user_id,
            token_package_id=purchase.token_package_id,
            billing_payment_id=purchase.billing_payment_id,
            status=purchase.status,
            tokens_amount=purchase.tokens_amount,
            bonus_tokens=purchase.bonus_tokens,
            total_tokens=(
                purchase.tokens_amount
                + purchase.bonus_tokens
            ),
            currency=purchase.currency,
            amount=purchase.amount,
            provider_checkout_session_id=(
                purchase.provider_checkout_session_id
            ),
            provider_payment_intent_id=(
                purchase.provider_payment_intent_id
            ),
            token_transaction_id=(
                purchase.token_transaction_id
            ),
            metadata=self._parse_json(
                purchase.metadata_json
            ),
            paid_at=purchase.paid_at,
            credited_at=purchase.credited_at,
            refunded_at=purchase.refunded_at,
            created_at=purchase.created_at,
            updated_at=purchase.updated_at,
        )

    def _payment_response(
        self,
        payment: BillingPayment,
    ) -> BillingPaymentResponse:
        return BillingPaymentResponse(
            id=payment.id,
            user_id=payment.user_id,
            billing_customer_id=payment.billing_customer_id,
            user_subscription_id=payment.user_subscription_id,
            provider=payment.provider,
            payment_type=payment.payment_type,
            status=payment.status,
            currency=payment.currency,
            amount=payment.amount,
            refunded_amount=payment.refunded_amount,
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
            metadata=self._parse_json(payment.metadata_json),
            paid_at=payment.paid_at,
            failed_at=payment.failed_at,
            refunded_at=payment.refunded_at,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
        )

    def get_purchase(
        self,
        db: Session,
        *,
        purchase_id: int,
    ) -> TokenPurchase:
        purchase = token_purchase_repository.get_by_id(
            db,
            purchase_id,
        )

        if not purchase:
            raise NotFoundException(
                "Token purchase not found."
            )

        return purchase

    def get_detail(
        self,
        db: Session,
        *,
        purchase_id: int,
        user_id: int | None = None,
    ) -> TokenPurchaseDetailResponse:
        purchase = self.get_purchase(
            db,
            purchase_id=purchase_id,
        )

        if user_id is not None and purchase.user_id != user_id:
            raise NotFoundException(
                "Token purchase not found."
            )

        payment = None

        if purchase.billing_payment_id:
            payment = billing_payment_repository.get_by_id(
                db,
                purchase.billing_payment_id,
            )

        return TokenPurchaseDetailResponse(
            purchase=self._purchase_response(purchase),
            payment=(
                self._payment_response(payment)
                if payment
                else None
            ),
        )

    def list_user_purchases(
        self,
        db: Session,
        *,
        user_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> TokenPurchaseListResponse:
        purchases = token_purchase_repository.list_by_user_id(
            db,
            user_id=user_id,
            skip=skip,
            limit=limit,
        )

        total = token_purchase_repository.count_by_user_id(
            db,
            user_id=user_id,
        )

        return TokenPurchaseListResponse(
            items=[
                self._purchase_response(purchase)
                for purchase in purchases
            ],
            total=total,
            skip=skip,
            limit=limit,
        )

    def list_admin_purchases(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        status: TokenPurchaseStatus | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> TokenPurchaseListResponse:
        status_value = status.value if status else None

        purchases = token_purchase_repository.list_all_filtered(
            db,
            user_id=user_id,
            status=status_value,
            skip=skip,
            limit=limit,
        )

        total = token_purchase_repository.count_filtered(
            db,
            user_id=user_id,
            status=status_value,
        )

        return TokenPurchaseListResponse(
            items=[
                self._purchase_response(purchase)
                for purchase in purchases
            ],
            total=total,
            skip=skip,
            limit=limit,
        )

    def create_checkout(
        self,
        db: Session,
        *,
        user: User,
        data: TokenPurchaseCheckoutRequest,
    ) -> TokenPurchaseCheckoutResponse:
        token_package = token_package_repository.get_by_id(
            db,
            data.token_package_id,
        )

        if not token_package:
            raise NotFoundException(
                "Token package not found."
            )

        if not token_package.is_active:
            raise ConflictException(
                "Token package is not active."
            )

        customer = (
            billing_customer_service
            .get_or_create_stripe_customer(
                db,
                user=user,
            )
        )

        currency = token_package.currency.upper()

        amount = (
            Decimal(token_package.price_cents)
            / Decimal("100")
        ).quantize(Decimal("0.01"))

        bonus_tokens = int(
            getattr(token_package, "bonus_tokens", 0) or 0
        )

        payment = BillingPayment(
            user_id=user.id,
            billing_customer_id=customer.id,
            provider=BillingProvider.STRIPE.value,
            payment_type=BillingPaymentType.TOKEN_PURCHASE.value,
            status=BillingPaymentStatus.PENDING.value,
            currency=currency,
            amount=amount,
            refunded_amount=Decimal("0.00"),
            description=(
                f"Token package purchase: "
                f"{token_package.name}"
            ),
            metadata_json=self._serialize_json(
                {
                    "token_package_id": token_package.id,
                }
            ),
        )

        db.add(payment)
        db.flush()

        purchase = TokenPurchase(
            user_id=user.id,
            token_package_id=token_package.id,
            billing_payment_id=payment.id,
            status=TokenPurchaseStatus.PENDING.value,
            tokens_amount=token_package.tokens_amount,
            bonus_tokens=bonus_tokens,
            currency=currency,
            amount=amount,
            metadata_json=self._serialize_json(
                {
                    "token_package_name": token_package.name,
                }
            ),
        )

        db.add(purchase)
        db.commit()
        db.refresh(payment)
        db.refresh(purchase)

        metadata = {
            "type": "token_purchase",
            "internal_user_id": str(user.id),
            "token_purchase_id": str(purchase.id),
            "billing_payment_id": str(payment.id),
            "token_package_id": str(token_package.id),
            "tokens_amount": str(purchase.tokens_amount),
            "bonus_tokens": str(purchase.bonus_tokens),
        }

        try:
            checkout_session = (
                stripe_client_service.create_checkout_session(
                    db,
                    customer_email=None,
                    customer_id=customer.provider_customer_id,
                    mode="payment",
                    line_items=[
                        {
                            "price_data": {
                                "currency": currency.lower(),
                                "product_data": {
                                    "name": token_package.name,
                                    **(
                                        {
                                            "description": token_package.description.strip(),
                                        }
                                        if token_package.description
                                        and token_package.description.strip()
                                        else {}
                                    ),
                                    "metadata": metadata,
                                },
                                "unit_amount": (
                                    token_package.price_cents
                                ),
                            },
                            "quantity": 1,
                        }
                    ],
                    success_url=str(data.success_url),
                    cancel_url=str(data.cancel_url),
                    metadata=metadata,
                    allow_promotion_codes=(
                        data.allow_promotion_codes
                    ),
                    client_reference_id=str(purchase.id),
                    idempotency_key=(
                        f"token-purchase-checkout-{purchase.id}"
                    ),
                )
            )

        except Exception as error:
            purchase.status = TokenPurchaseStatus.FAILED.value
            payment.status = BillingPaymentStatus.FAILED.value
            payment.failure_message = str(error)
            payment.failed_at = utc_now()

            db.add(purchase)
            db.add(payment)
            db.commit()

            raise

        checkout_session_id = checkout_session.id

        purchase.provider_checkout_session_id = (
            checkout_session_id
        )

        payment.provider_checkout_session_id = (
            checkout_session_id
        )

        db.add(purchase)
        db.add(payment)
        db.commit()
        db.refresh(purchase)
        db.refresh(payment)

        integration_service.record_event(
            db,
            provider=BillingProvider.STRIPE.value,
            event_type="token_purchase.checkout_created",
            entity_type="token_purchase",
            entity_id=str(purchase.id),
            payload=metadata,
            response={
                "checkout_session_id": (
                    checkout_session_id
                ),
                "checkout_url": checkout_session.url,
            },
        )

        return TokenPurchaseCheckoutResponse(
            token_purchase_id=purchase.id,
            billing_payment_id=payment.id,
            checkout_session_id=checkout_session_id,
            checkout_url=checkout_session.url,
            status=purchase.status,
        )

    def process_checkout_completed(
        self,
        db: Session,
        *,
        checkout_session: Any,
    ) -> TokenPurchase:
        checkout_session_id = self._stripe_value(
            checkout_session,
            "id",
        )

        metadata = self._stripe_value(
            checkout_session,
            "metadata",
            {},
        ) or {}

        purchase_id = self._stripe_int(
            metadata,
            "token_purchase_id",
        )

        if purchase_id is not None:
            purchase = token_purchase_repository.get_for_update(
                db,
                purchase_id,
            )
        else:
            purchase = (
                token_purchase_repository
                .get_by_checkout_session_id(
                    db,
                    checkout_session_id,
                )
            )

        if not purchase:
            raise NotFoundException(
                "Token purchase for Checkout Session was not found."
            )

        payment = billing_payment_repository.get_for_update(
            db,
            purchase.billing_payment_id,
        )

        if not payment:
            raise NotFoundException(
                "Billing payment was not found."
            )

        payment_status = self._stripe_value(
            checkout_session,
            "payment_status",
        )

        if payment_status != "paid":
            purchase.status = TokenPurchaseStatus.PENDING.value
            payment.status = BillingPaymentStatus.PROCESSING.value

            db.add(purchase)
            db.add(payment)
            db.commit()

            return purchase

        payment_intent = self._stripe_value(
            checkout_session,
            "payment_intent",
        )

        if not isinstance(payment_intent, str):
            payment_intent = self._stripe_value(
                payment_intent,
                "id",
            )

        now = utc_now()

        purchase.provider_payment_intent_id = payment_intent
        purchase.paid_at = purchase.paid_at or now

        payment.provider_payment_intent_id = payment_intent
        payment.status = BillingPaymentStatus.SUCCEEDED.value
        payment.paid_at = payment.paid_at or now

        if purchase.status == TokenPurchaseStatus.CREDITED.value:
            db.add(purchase)
            db.add(payment)
            db.commit()
            db.refresh(purchase)

            return purchase

        purchase.status = TokenPurchaseStatus.PAID.value

        db.add(purchase)
        db.add(payment)
        db.flush()

        total_tokens = (
            purchase.tokens_amount
            + purchase.bonus_tokens
        )

        token_service.credit_tokens(
            db=db,
            user_id=purchase.user_id,
            amount=total_tokens,
            source="stripe_token_purchase",
            reference_id=str(purchase.id),
            description=(
                f"Token purchase #{purchase.id}"
            ),
        )

        purchase.status = TokenPurchaseStatus.CREDITED.value
        purchase.credited_at = now

        db.add(purchase)
        db.add(payment)
        db.commit()
        db.refresh(purchase)

        return purchase

    def mark_checkout_failed(
        self,
        db: Session,
        *,
        checkout_session: Any,
        error_message: str | None = None,
    ) -> TokenPurchase | None:
        checkout_session_id = self._stripe_value(
            checkout_session,
            "id",
        )

        metadata = self._stripe_value(
            checkout_session,
            "metadata",
            {},
        ) or {}

        purchase_id = self._stripe_int(
            metadata,
            "token_purchase_id",
        )

        if purchase_id is not None:
            purchase = token_purchase_repository.get_by_id(
                db,
                purchase_id,
            )
        else:
            purchase = (
                token_purchase_repository
                .get_by_checkout_session_id(
                    db,
                    checkout_session_id,
                )
            )

        if not purchase:
            return None

        payment = None

        if purchase.billing_payment_id:
            payment = billing_payment_repository.get_by_id(
                db,
                purchase.billing_payment_id,
            )

        if purchase.status != TokenPurchaseStatus.CREDITED.value:
            purchase.status = TokenPurchaseStatus.FAILED.value

        if payment and payment.status != BillingPaymentStatus.SUCCEEDED.value:
            payment.status = BillingPaymentStatus.FAILED.value
            payment.failure_message = (
                error_message
                or "Stripe Checkout payment failed."
            )
            payment.failed_at = utc_now()
            db.add(payment)

        db.add(purchase)
        db.commit()
        db.refresh(purchase)

        return purchase

    def reconcile(
        self,
        db: Session,
        *,
        purchase_id: int,
        force: bool = False,
    ) -> TokenPurchaseReconcileResponse:
        purchase = self.get_purchase(
            db,
            purchase_id=purchase_id,
        )

        if (
            purchase.status
            == TokenPurchaseStatus.CREDITED.value
            and not force
        ):
            payment = (
                billing_payment_repository.get_by_id(
                    db,
                    purchase.billing_payment_id,
                )
                if purchase.billing_payment_id
                else None
            )

            return TokenPurchaseReconcileResponse(
                purchase=self._purchase_response(purchase),
                payment=(
                    self._payment_response(payment)
                    if payment
                    else None
                ),
                reconciled=False,
                message="Purchase was already credited.",
            )

        if not purchase.provider_checkout_session_id:
            raise ConflictException(
                "Purchase has no Stripe Checkout Session."
            )

        checkout_session = (
            stripe_client_service.retrieve_checkout_session(
                db,
                checkout_session_id=(
                    purchase.provider_checkout_session_id
                ),
            )
        )

        updated = self.process_checkout_completed(
            db,
            checkout_session=checkout_session,
        )

        payment = (
            billing_payment_repository.get_by_id(
                db,
                updated.billing_payment_id,
            )
            if updated.billing_payment_id
            else None
        )

        return TokenPurchaseReconcileResponse(
            purchase=self._purchase_response(updated),
            payment=(
                self._payment_response(payment)
                if payment
                else None
            ),
            reconciled=True,
            message="Token purchase reconciled with Stripe.",
        )

    def refund(
        self,
        db: Session,
        *,
        purchase_id: int,
        data: TokenPurchaseRefundRequest,
    ) -> TokenPurchaseRefundResponse:
        purchase = token_purchase_repository.get_for_update(
            db,
            purchase_id,
        )

        if not purchase:
            raise NotFoundException(
                "Token purchase not found."
            )

        if not purchase.billing_payment_id:
            raise ConflictException(
                "Purchase has no billing payment."
            )

        payment = billing_payment_repository.get_for_update(
            db,
            purchase.billing_payment_id,
        )

        if not payment:
            raise NotFoundException(
                "Billing payment not found."
            )

        if not payment.provider_payment_intent_id:
            raise ConflictException(
                "Payment has no Stripe PaymentIntent."
            )

        if payment.status not in [
            BillingPaymentStatus.SUCCEEDED.value,
            BillingPaymentStatus.PARTIALLY_REFUNDED.value,
        ]:
            raise ConflictException(
                "Payment cannot be refunded in its current state."
            )

        remaining_refundable = (
            payment.amount - payment.refunded_amount
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
            raise ConflictException(
                "Refund amount exceeds the remaining refundable amount."
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
                    "token_purchase_id": str(purchase.id),
                    "billing_payment_id": str(payment.id),
                },
                idempotency_key=(
                    f"token-purchase-refund-"
                    f"{purchase.id}-"
                    f"{self._money_to_cents(refund_amount)}-"
                    f"{self._money_to_cents(payment.refunded_amount)}"
                ),
            )
        )

        new_refunded_amount = (
            payment.refunded_amount + refund_amount
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

        total_tokens = (
            purchase.tokens_amount
            + purchase.bonus_tokens
        )

        removed_tokens = 0

        if data.remove_tokens and total_tokens > 0:
            ratio = refund_amount / payment.amount

            removed_tokens = int(
                (
                    Decimal(total_tokens) * ratio
                ).quantize(
                    Decimal("1"),
                    rounding=ROUND_HALF_UP,
                )
            )

            if fully_refunded:
                removed_tokens = total_tokens

            if removed_tokens > 0:
                token_service.debit_tokens(
                    db=db,
                    user_id=purchase.user_id,
                    amount=removed_tokens,
                    source="stripe_token_refund",
                    reference_id=str(purchase.id),
                    description=(
                        f"Token removal for refund "
                        f"of purchase #{purchase.id}"
                    ),
                )

        if fully_refunded:
            purchase.status = TokenPurchaseStatus.REFUNDED.value
            purchase.refunded_at = utc_now()

        purchase.metadata_json = self._serialize_json(
            {
                **self._parse_json(purchase.metadata_json),
                "last_refund_id": self._stripe_value(
                    stripe_refund,
                    "id",
                ),
                "last_refund_amount": str(refund_amount),
                "last_removed_tokens": removed_tokens,
            }
        )

        db.add(payment)
        db.add(purchase)
        db.commit()
        db.refresh(payment)
        db.refresh(purchase)

        integration_service.record_event(
            db,
            provider=BillingProvider.STRIPE.value,
            event_type="token_purchase.refunded",
            entity_type="token_purchase",
            entity_id=str(purchase.id),
            payload={
                "refund_amount": str(refund_amount),
                "reason": data.reason,
                "remove_tokens": data.remove_tokens,
            },
            response={
                "stripe_refund_id": self._stripe_value(
                    stripe_refund,
                    "id",
                ),
                "removed_tokens": removed_tokens,
                "fully_refunded": fully_refunded,
            },
        )

        return TokenPurchaseRefundResponse(
            purchase=self._purchase_response(purchase),
            payment=self._payment_response(payment),
            stripe_refund_id=self._stripe_value(
                stripe_refund,
                "id",
            ),
            refunded_amount=refund_amount,
            removed_tokens=removed_tokens,
            message=(
                "Token purchase refunded successfully."
            ),
        )


token_purchase_service = TokenPurchaseService()