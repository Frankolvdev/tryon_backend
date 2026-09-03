from __future__ import annotations

from pathlib import Path
import re
import shutil
import sys


TARGET = Path("app/services/billing_invoice_service.py")

NEW_SYNC = r'''    def _payment_intent_id(
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
            self._stripe_value(
                stripe_invoice,
                "payments",
                {},
            )
            or {}
        )
        entries = (
            self._stripe_value(
                payments,
                "data",
                [],
            )
            or []
        )

        for entry in entries:
            payment = (
                self._stripe_value(
                    entry,
                    "payment",
                    {},
                )
                or {}
            )
            payment_type = self._stripe_value(
                payment,
                "type",
            )
            if payment_type not in {
                None,
                "payment_intent",
            }:
                continue

            payment_intent_id = self._stripe_id(
                self._stripe_value(
                    payment,
                    "payment_intent",
                )
            )
            if payment_intent_id:
                return payment_intent_id

            payment_intent_id = self._stripe_id(
                self._stripe_value(
                    entry,
                    "payment_intent",
                )
            )
            if payment_intent_id:
                return payment_intent_id

        return None

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
        if not provider_invoice_id:
            raise ValueError("Stripe invoice ID is required.")

        existing = (
            billing_invoice_repository
            .get_by_provider_invoice_id(
                db,
                provider_invoice_id,
            )
        )

        customer_id = self._stripe_id(
            self._stripe_value(
                stripe_invoice,
                "customer",
            )
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
        elif existing:
            user_id = existing.user_id

        if user_id is None:
            raise ValueError(
                "Internal user could not be resolved for invoice."
            )

        payment_intent_id = self._payment_intent_id(
            stripe_invoice
        )

        payment = None
        if existing and existing.billing_payment_id:
            payment = billing_payment_repository.get_by_id(
                db,
                existing.billing_payment_id,
            )

        if payment is None and payment_intent_id:
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

        billing_reason = self._stripe_value(
            stripe_invoice,
            "billing_reason",
        )
        payment_type = (
            BillingPaymentType.SUBSCRIPTION.value
            if billing_reason == "subscription_create"
            else BillingPaymentType.SUBSCRIPTION_RENEWAL.value
        )
        payment_status = (
            BillingPaymentStatus.SUCCEEDED.value
            if invoice_status == BillingInvoiceStatus.PAID.value
            else BillingPaymentStatus.PROCESSING.value
        )

        should_create_payment = (
            payment is None
            and (
                payment_intent_id is not None
                or invoice_status == BillingInvoiceStatus.PAID.value
                or amount_paid > Decimal("0.00")
            )
        )

        if should_create_payment:
            payment = BillingPayment(
                user_id=user_id,
                billing_customer_id=(
                    billing_customer.id
                    if billing_customer
                    else (
                        existing.billing_customer_id
                        if existing
                        else None
                    )
                ),
                user_subscription_id=(
                    user_subscription.id
                    if user_subscription
                    else (
                        existing.user_subscription_id
                        if existing
                        else None
                    )
                ),
                provider=BillingProvider.STRIPE.value,
                payment_type=payment_type,
                status=payment_status,
                currency=currency,
                amount=amount_paid or total,
                refunded_amount=Decimal("0.00"),
                provider_payment_intent_id=payment_intent_id,
                description=(
                    f"Stripe invoice {provider_invoice_id}"
                ),
                metadata_json=self._serialize(
                    {
                        "provider_invoice_id": provider_invoice_id,
                        "billing_reason": billing_reason,
                        "payment_intent_source": (
                            "invoice.payment_intent"
                            if self._stripe_id(
                                self._stripe_value(
                                    stripe_invoice,
                                    "payment_intent",
                                )
                            )
                            else (
                                "invoice.payments.data"
                                if payment_intent_id
                                else "invoice_fallback"
                            )
                        ),
                    }
                ),
                paid_at=(
                    self._timestamp(
                        self._stripe_value(
                            self._stripe_value(
                                stripe_invoice,
                                "status_transitions",
                                {},
                            ),
                            "paid_at",
                        )
                    )
                    or (
                        utc_now()
                        if payment_status
                        == BillingPaymentStatus.SUCCEEDED.value
                        else None
                    )
                ),
            )
            db.add(payment)
            db.flush()
        elif payment:
            payment.user_id = user_id
            payment.billing_customer_id = (
                billing_customer.id
                if billing_customer
                else payment.billing_customer_id
            )
            payment.user_subscription_id = (
                user_subscription.id
                if user_subscription
                else payment.user_subscription_id
            )
            payment.payment_type = payment_type
            payment.amount = amount_paid or total
            payment.currency = currency
            if (
                payment.provider_payment_intent_id is None
                and payment_intent_id
            ):
                payment.provider_payment_intent_id = (
                    payment_intent_id
                )
            if invoice_status == BillingInvoiceStatus.PAID.value:
                payment.status = (
                    BillingPaymentStatus.SUCCEEDED.value
                )
                payment.paid_at = (
                    payment.paid_at
                    or self._timestamp(
                        self._stripe_value(
                            self._stripe_value(
                                stripe_invoice,
                                "status_transitions",
                                {},
                            ),
                            "paid_at",
                        )
                    )
                    or utc_now()
                )
                payment.failure_code = None
                payment.failure_message = None
                payment.failed_at = None
            db.add(payment)
            db.flush()

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
                else (
                    existing.billing_customer_id
                    if existing
                    else None
                )
            ),
            "user_subscription_id": (
                user_subscription.id
                if user_subscription
                else (
                    existing.user_subscription_id
                    if existing
                    else None
                )
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
                self._stripe_dict(
                    self._stripe_value(
                        stripe_invoice,
                        "metadata",
                        {},
                    )
                )
            ),
        }

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

'''


def main() -> int:
    if not TARGET.exists():
        print(
            f"ERROR: No se encontró {TARGET}. "
            "Ejecuta este script desde la raíz de tryon_backend.",
            file=sys.stderr,
        )
        return 1

    source = TARGET.read_text(encoding="utf-8")
    pattern = re.compile(
        r"    def sync_invoice\(\n.*?"
        r"(?=    def mark_payment_failed\()",
        re.DOTALL,
    )
    match = pattern.search(source)
    if not match:
        print(
            "ERROR: No se encontró sync_invoice con "
            "la estructura esperada.",
            file=sys.stderr,
        )
        return 1

    updated = (
        source[:match.start()]
        + NEW_SYNC
        + source[match.end():]
    )

    backup = TARGET.with_suffix(".py.09S11.bak")
    if not backup.exists():
        shutil.copy2(TARGET, backup)

    TARGET.write_text(updated, encoding="utf-8")
    print(
        "OK: billing_invoice_service.py actualizado "
        "para Stripe moderno."
    )
    print(f"Backup: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
