from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import stripe
from sqlalchemy.orm import Session

from app.common.enums import IntegrationProvider
from app.common.exceptions import ConflictException
from app.services.billing_invoice_policy_service import (
    billing_invoice_policy_service,
)
from app.services.integration_service import integration_service


class StripeClientService:
    def _get_config(self, db: Session):
        config = integration_service.get_config(
            db,
            IntegrationProvider.STRIPE,
        )
        if not config.is_enabled:
            raise ConflictException("Stripe integration is disabled.")
        if not config.api_key:
            raise ConflictException("Stripe API key is not configured.")
        stripe.api_key = config.api_key
        return config

    def _money_to_cents(self, amount: Decimal) -> int:
        normalized = amount.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        return int(normalized * 100)

    def _datetime_to_timestamp(
        self,
        value: datetime | None,
    ) -> int | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return int(value.timestamp())

    def create_customer(
        self,
        db: Session,
        *,
        email: str,
        name: str | None,
        metadata: dict[str, str],
    ):
        self._get_config(db)
        payload: dict[str, Any] = {
            "email": email,
            "metadata": metadata,
        }
        if name:
            payload["name"] = name
        return stripe.Customer.create(**payload)

    def retrieve_customer(
        self,
        db: Session,
        *,
        customer_id: str,
    ):
        self._get_config(db)
        return stripe.Customer.retrieve(customer_id)

    def update_customer(
        self,
        db: Session,
        *,
        customer_id: str,
        email: str,
        name: str | None,
        metadata: dict[str, str],
    ):
        self._get_config(db)
        payload: dict[str, Any] = {
            "email": email,
            "metadata": metadata,
        }
        if name is not None:
            payload["name"] = name
        return stripe.Customer.modify(customer_id, **payload)

    def create_product(
        self,
        db: Session,
        *,
        name: str,
        description: str | None,
        metadata: dict[str, str],
        active: bool = True,
    ):
        self._get_config(db)
        payload: dict[str, Any] = {
            "name": name,
            "active": active,
            "metadata": metadata,
        }
        if description:
            payload["description"] = description
        return stripe.Product.create(**payload)

    def update_product(
        self,
        db: Session,
        *,
        product_id: str,
        name: str,
        description: str | None,
        metadata: dict[str, str],
        active: bool,
    ):
        self._get_config(db)
        return stripe.Product.modify(
            product_id,
            name=name,
            description=description or "",
            metadata=metadata,
            active=active,
        )

    def retrieve_product(
        self,
        db: Session,
        *,
        product_id: str,
    ):
        self._get_config(db)
        return stripe.Product.retrieve(product_id)

    def create_recurring_price(
        self,
        db: Session,
        *,
        product_id: str,
        currency: str,
        unit_amount_cents: int,
        interval: str,
        nickname: str,
        metadata: dict[str, str],
    ):
        self._get_config(db)
        return stripe.Price.create(
            product=product_id,
            currency=currency.lower(),
            unit_amount=unit_amount_cents,
            recurring={"interval": interval},
            nickname=nickname,
            metadata=metadata,
        )

    def retrieve_price(
        self,
        db: Session,
        *,
        price_id: str,
    ):
        self._get_config(db)
        return stripe.Price.retrieve(price_id)

    def deactivate_price(
        self,
        db: Session,
        *,
        price_id: str,
    ):
        self._get_config(db)
        return stripe.Price.modify(price_id, active=False)

    def activate_price(
        self,
        db: Session,
        *,
        price_id: str,
    ):
        self._get_config(db)
        return stripe.Price.modify(price_id, active=True)

    def create_coupon(
        self,
        db: Session,
        *,
        name: str,
        discount_type: str,
        percentage_off: Decimal | None,
        amount_off: Decimal | None,
        currency: str | None,
        duration: str,
        duration_in_months: int | None,
        max_redemptions: int | None,
        redeem_by: datetime | None,
        metadata: dict[str, str],
        idempotency_key: str,
    ):
        self._get_config(db)
        payload: dict[str, Any] = {
            "name": name,
            "duration": duration,
            "metadata": metadata,
        }
        if discount_type == "percentage":
            payload["percent_off"] = float(percentage_off)
        else:
            payload["amount_off"] = self._money_to_cents(amount_off)
            payload["currency"] = currency.lower()
        if duration == "repeating":
            payload["duration_in_months"] = duration_in_months
        if max_redemptions is not None:
            payload["max_redemptions"] = max_redemptions
        redeem_by_timestamp = self._datetime_to_timestamp(redeem_by)
        if redeem_by_timestamp is not None:
            payload["redeem_by"] = redeem_by_timestamp
        return stripe.Coupon.create(
            **payload,
            idempotency_key=idempotency_key,
        )

    def create_promotion_code(
        self,
        db: Session,
        *,
        coupon_id: str,
        code: str,
        active: bool,
        max_redemptions: int | None,
        expires_at: datetime | None,
        first_time_transaction_only: bool,
        minimum_amount: Decimal | None,
        minimum_amount_currency: str | None,
        metadata: dict[str, str],
        idempotency_key: str,
    ):
        self._get_config(db)
        restrictions: dict[str, Any] = {
            "first_time_transaction": first_time_transaction_only,
        }
        if minimum_amount is not None:
            restrictions["minimum_amount"] = self._money_to_cents(
                minimum_amount
            )
            restrictions["minimum_amount_currency"] = (
                minimum_amount_currency.lower()
            )
        payload: dict[str, Any] = {
            "promotion": {
                "type": "coupon",
                "coupon": coupon_id,
            },
            "code": code,
            "active": active,
            "restrictions": restrictions,
            "metadata": metadata,
        }
        if max_redemptions is not None:
            payload["max_redemptions"] = max_redemptions
        expires_at_timestamp = self._datetime_to_timestamp(expires_at)
        if expires_at_timestamp is not None:
            payload["expires_at"] = expires_at_timestamp
        return stripe.PromotionCode.create(
            **payload,
            idempotency_key=idempotency_key,
        )

    def update_promotion_code_active(
        self,
        db: Session,
        *,
        promotion_code_id: str,
        active: bool,
        metadata: dict[str, str],
    ):
        self._get_config(db)
        return stripe.PromotionCode.modify(
            promotion_code_id,
            active=active,
            metadata=metadata,
        )

    def _sanitize_checkout_line_items(
        self,
        line_items: list[dict],
    ) -> list[dict]:
        """Remove optional empty values that Stripe rejects."""
        sanitized_items: list[dict] = []
        for item in line_items:
            sanitized_item = dict(item)
            price_data = sanitized_item.get("price_data")
            if isinstance(price_data, dict):
                sanitized_price_data = dict(price_data)
                product_data = sanitized_price_data.get("product_data")
                if isinstance(product_data, dict):
                    sanitized_product_data = dict(product_data)
                    description = sanitized_product_data.get("description")
                    if (
                        not isinstance(description, str)
                        or not description.strip()
                    ):
                        sanitized_product_data.pop("description", None)
                    else:
                        sanitized_product_data["description"] = (
                            description.strip()
                        )

                    images = sanitized_product_data.get("images")
                    if isinstance(images, list):
                        clean_images = [
                            image.strip()
                            for image in images
                            if isinstance(image, str) and image.strip()
                        ]
                        if clean_images:
                            sanitized_product_data["images"] = clean_images
                        else:
                            sanitized_product_data.pop("images", None)

                    product_metadata = sanitized_product_data.get("metadata")
                    if isinstance(product_metadata, dict):
                        clean_product_metadata = {
                            str(key): str(value)
                            for key, value in product_metadata.items()
                            if value is not None and str(value).strip()
                        }
                        if clean_product_metadata:
                            sanitized_product_data["metadata"] = (
                                clean_product_metadata
                            )
                        else:
                            sanitized_product_data.pop("metadata", None)

                    sanitized_price_data["product_data"] = (
                        sanitized_product_data
                    )
                sanitized_item["price_data"] = sanitized_price_data
            sanitized_items.append(sanitized_item)
        return sanitized_items

    def create_checkout_session(
        self,
        db: Session,
        *,
        customer_email: str | None,
        customer_id: str | None = None,
        mode: str,
        line_items: list[dict],
        success_url: str,
        cancel_url: str,
        metadata: dict[str, str],
        allow_promotion_codes: bool = False,
        subscription_metadata: dict[str, str] | None = None,
        client_reference_id: str | None = None,
        idempotency_key: str | None = None,
        promotion_code_id: str | None = None,
    ):
        self._get_config(db)

        checkout_metadata = {
            str(key): str(value)
            for key, value in metadata.items()
            if value is not None
        }
        payload: dict[str, Any] = {
            "mode": mode,
            "line_items": self._sanitize_checkout_line_items(line_items),
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": checkout_metadata,
        }

        if promotion_code_id:
            payload["discounts"] = [
                {"promotion_code": promotion_code_id}
            ]
        else:
            payload["allow_promotion_codes"] = allow_promotion_codes

        if customer_id:
            payload["customer"] = customer_id
        elif customer_email:
            payload["customer_email"] = customer_email

        if client_reference_id:
            payload["client_reference_id"] = client_reference_id

        if mode == "subscription" and subscription_metadata:
            payload["subscription_data"] = {
                "metadata": subscription_metadata,
            }

        if mode == "payment":
            invoice_enabled, invoice_category = (
                billing_invoice_policy_service.checkout_invoice_enabled(
                    db,
                    checkout_metadata,
                )
            )
            if invoice_category:
                checkout_metadata["invoice_category"] = invoice_category
                checkout_metadata["invoice_enabled"] = (
                    "true" if invoice_enabled else "false"
                )
                payload["metadata"] = checkout_metadata

            payload["payment_intent_data"] = {
                "metadata": checkout_metadata,
            }

            if invoice_enabled:
                payload["invoice_creation"] = {
                    "enabled": True,
                    "invoice_data": {
                        "metadata": checkout_metadata,
                    },
                }

        request_options: dict[str, Any] = {}
        if idempotency_key:
            request_options["idempotency_key"] = idempotency_key

        return stripe.checkout.Session.create(
            **payload,
            **request_options,
        )

    def retrieve_checkout_session(
        self,
        db: Session,
        *,
        checkout_session_id: str,
    ):
        self._get_config(db)
        return stripe.checkout.Session.retrieve(
            checkout_session_id,
            expand=[
                "payment_intent",
                "customer",
                "subscription",
            ],
        )

    def expire_checkout_session(
        self,
        db: Session,
        *,
        checkout_session_id: str,
    ):
        self._get_config(db)
        return stripe.checkout.Session.expire(checkout_session_id)

    def retrieve_payment_intent(
        self,
        db: Session,
        *,
        payment_intent_id: str,
    ):
        self._get_config(db)
        return stripe.PaymentIntent.retrieve(
            payment_intent_id,
            expand=["latest_charge"],
        )

    def create_customer_portal_session(
        self,
        db: Session,
        *,
        customer_id: str,
        return_url: str,
    ):
        self._get_config(db)
        return stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )

    def retrieve_subscription(
        self,
        db: Session,
        *,
        subscription_id: str,
    ):
        self._get_config(db)
        return stripe.Subscription.retrieve(
            subscription_id,
            expand=["items.data.price"],
        )

    def update_subscription_cancel_at_period_end(
        self,
        db: Session,
        *,
        subscription_id: str,
        cancel_at_period_end: bool,
    ):
        self._get_config(db)
        return stripe.Subscription.modify(
            subscription_id,
            cancel_at_period_end=cancel_at_period_end,
        )

    def cancel_subscription_immediately(
        self,
        db: Session,
        *,
        subscription_id: str,
        invoice_now: bool = False,
        prorate: bool = False,
    ):
        self._get_config(db)
        return stripe.Subscription.cancel(
            subscription_id,
            invoice_now=invoice_now,
            prorate=prorate,
        )

    def change_subscription_price(
        self,
        db: Session,
        *,
        subscription_id: str,
        subscription_item_id: str,
        new_price_id: str,
        proration_behavior: str,
    ):
        self._get_config(db)
        return stripe.Subscription.modify(
            subscription_id,
            items=[
                {
                    "id": subscription_item_id,
                    "price": new_price_id,
                }
            ],
            proration_behavior=proration_behavior,
            cancel_at_period_end=False,
            metadata={"last_plan_change_source": "api"},
            expand=["items.data.price"],
        )

    def construct_webhook_event(
        self,
        db: Session,
        *,
        payload: bytes,
        signature_header: str | None,
    ):
        config = self._get_config(db)
        if not config.webhook_secret:
            raise ConflictException(
                "Stripe webhook secret is not configured."
            )
        if not signature_header:
            raise ConflictException(
                "Stripe signature header is missing."
            )
        return stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature_header,
            secret=config.webhook_secret,
        )

    def refund_payment_intent(
        self,
        db: Session,
        *,
        payment_intent_id: str,
        amount_cents: int | None = None,
        reason: str | None = None,
        metadata: dict[str, str] | None = None,
        idempotency_key: str | None = None,
    ):
        self._get_config(db)
        payload: dict[str, Any] = {
            "payment_intent": payment_intent_id,
        }
        if amount_cents is not None:
            payload["amount"] = amount_cents
        if reason:
            payload["reason"] = reason
        if metadata:
            payload["metadata"] = metadata

        request_options: dict[str, Any] = {}
        if idempotency_key:
            request_options["idempotency_key"] = idempotency_key

        return stripe.Refund.create(
            **payload,
            **request_options,
        )


stripe_client_service = StripeClientService()
