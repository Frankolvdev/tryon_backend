import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.billing_invoice import BillingInvoice
from app.models.billing_payment import BillingPayment
from app.services.system_setting_service import system_setting_service


SUBSCRIPTION_INVOICES_KEY = "billing_invoice_subscriptions_enabled"
TOKEN_PACKAGE_INVOICES_KEY = "billing_invoice_token_packages_enabled"
CUSTOM_TOKEN_INVOICES_KEY = "billing_invoice_custom_tokens_enabled"


class BillingInvoicePolicyService:
    def _enabled(self, db: Session, key: str) -> bool:
        value = system_setting_service.get_value(db, key, False)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def subscriptions_enabled(self, db: Session) -> bool:
        return self._enabled(db, SUBSCRIPTION_INVOICES_KEY)

    def token_packages_enabled(self, db: Session) -> bool:
        return self._enabled(db, TOKEN_PACKAGE_INVOICES_KEY)

    def custom_tokens_enabled(self, db: Session) -> bool:
        return self._enabled(db, CUSTOM_TOKEN_INVOICES_KEY)

    def checkout_invoice_enabled(
        self,
        db: Session,
        metadata: dict[str, Any] | None,
    ) -> tuple[bool, str | None]:
        metadata = metadata or {}
        if metadata.get("type") != "token_purchase":
            return False, None

        purchase_kind = str(metadata.get("purchase_kind") or "").lower()
        if purchase_kind == "package":
            return self.token_packages_enabled(db), "token_package"
        if purchase_kind == "custom":
            return self.custom_tokens_enabled(db), "custom_tokens"
        return False, None

    def _parse(self, value: str | None) -> dict[str, Any]:
        if not value:
            return {}
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _category_enabled(
        self,
        db: Session,
        category: str | None,
    ) -> bool:
        if category == "subscription":
            return self.subscriptions_enabled(db)
        if category == "token_package":
            return self.token_packages_enabled(db)
        if category == "custom_tokens":
            return self.custom_tokens_enabled(db)
        return False

    def payment_documents_enabled(
        self,
        db: Session,
        payment: BillingPayment,
    ) -> bool:
        if payment.payment_type in {"subscription", "subscription_renewal"}:
            return self.subscriptions_enabled(db)

        metadata = self._parse(payment.metadata_json)
        category = metadata.get("invoice_category")
        if category:
            return self._category_enabled(db, str(category))

        purchase_kind = metadata.get("purchase_kind")
        if purchase_kind == "package":
            return self.token_packages_enabled(db)
        if purchase_kind == "custom":
            return self.custom_tokens_enabled(db)
        return False

    def invoice_documents_enabled(
        self,
        db: Session,
        invoice: BillingInvoice,
    ) -> bool:
        metadata = self._parse(invoice.metadata_json)
        category = metadata.get("invoice_category")
        if category:
            return self._category_enabled(db, str(category))

        if invoice.user_subscription_id:
            return self.subscriptions_enabled(db)

        if invoice.billing_payment_id:
            payment = db.get(BillingPayment, invoice.billing_payment_id)
            if payment:
                return self.payment_documents_enabled(db, payment)
        return False


billing_invoice_policy_service = BillingInvoicePolicyService()
