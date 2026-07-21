import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.billing_payment import BillingPayment


class BillingPaymentMethodService:
    def _value(
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

    def _parse(self, value: str | None) -> dict[str, Any]:
        if not value:
            return {}
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _serialize(self, value: dict[str, Any]) -> str:
        return json.dumps(value, ensure_ascii=False, default=str)

    def is_hydrated(self, payment: BillingPayment) -> bool:
        metadata = self._parse(payment.metadata_json)
        return bool(metadata.get("payment_method_hydrated"))

    def details_from_payment(
        self,
        payment: BillingPayment,
    ) -> dict[str, str | None]:
        metadata = self._parse(payment.metadata_json)
        return {
            "payment_method_type": metadata.get("payment_method_type"),
            "payment_method_brand": metadata.get("payment_method_brand"),
            "payment_method_last4": metadata.get("payment_method_last4"),
            "payment_method_wallet": metadata.get("payment_method_wallet"),
        }

    def apply_from_payment_intent(
        self,
        db: Session,
        *,
        payment: BillingPayment,
        payment_intent: Any,
        retrieve_if_needed: bool = True,
    ) -> BillingPayment:
        latest_charge = self._value(payment_intent, "latest_charge")

        if isinstance(latest_charge, str) and retrieve_if_needed:
            from app.services.stripe_client_service import stripe_client_service

            payment_intent_id = self._value(payment_intent, "id")
            if payment_intent_id:
                payment_intent = stripe_client_service.retrieve_payment_intent(
                    db,
                    payment_intent_id=payment_intent_id,
                )
                latest_charge = self._value(payment_intent, "latest_charge")

        charge_id = (
            latest_charge
            if isinstance(latest_charge, str)
            else self._value(latest_charge, "id")
        )
        if charge_id:
            payment.provider_charge_id = charge_id

        details = self._value(
            latest_charge,
            "payment_method_details",
            {},
        ) or {}
        method_type = self._value(details, "type")
        card = self._value(details, "card", {}) or {}
        brand = self._value(card, "brand")
        last4 = self._value(card, "last4")
        wallet = self._value(
            self._value(card, "wallet", {}) or {},
            "type",
        )

        metadata = self._parse(payment.metadata_json)
        metadata["payment_method_hydrated"] = True
        if method_type:
            metadata["payment_method_type"] = str(method_type)
        if brand:
            metadata["payment_method_brand"] = str(brand)
        if last4:
            metadata["payment_method_last4"] = str(last4)
        if wallet:
            metadata["payment_method_wallet"] = str(wallet)

        payment.metadata_json = self._serialize(metadata)
        return payment


billing_payment_method_service = BillingPaymentMethodService()
