from __future__ import annotations

from pathlib import Path
import re
import shutil
import sys


TARGET = Path("app/services/billing_service.py")

MODEL_IMPORT = "from app.models.billing_payment import BillingPayment\n"

NEW_INVOICE_PAID = r'''    def _invoice_paid(
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
                billing_invoice_service
                .provider_subscription_id(
                    event_object
                )
            )
            if provider_subscription_id:
                (
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

        payment_intent = self._value(
            event_object,
            "payment_intent",
        )
        payment_intent_id = (
            payment_intent
            if isinstance(payment_intent, str)
            else self._value(payment_intent, "id")
        )

        payment = None
        if payment_intent_id and invoice.user_id:
            payment = (
                billing_payment_repository
                .get_by_payment_intent_id(
                    db,
                    payment_intent_id,
                )
            )

            billing_reason = self._value(
                event_object,
                "billing_reason",
            )
            payment_type = (
                "subscription"
                if billing_reason == "subscription_create"
                else "subscription_renewal"
            )

            charge = self._value(
                event_object,
                "charge",
            )
            charge_id = (
                charge
                if isinstance(charge, str)
                else self._value(charge, "id")
            )

            if payment is None:
                payment = BillingPayment(
                    user_id=invoice.user_id,
                    billing_customer_id=(
                        invoice.billing_customer_id
                    ),
                    user_subscription_id=(
                        invoice.user_subscription_id
                    ),
                    provider=invoice.provider,
                    payment_type=payment_type,
                    status=(
                        BillingPaymentStatus
                        .SUCCEEDED
                        .value
                    ),
                    currency=invoice.currency,
                    amount=invoice.amount_paid,
                    provider_payment_intent_id=(
                        payment_intent_id
                    ),
                    provider_charge_id=charge_id,
                    description=(
                        "Subscription payment"
                        if payment_type == "subscription"
                        else "Subscription renewal"
                    ),
                    paid_at=invoice.paid_at or utc_now(),
                )
            else:
                payment.user_id = invoice.user_id
                payment.billing_customer_id = (
                    invoice.billing_customer_id
                )
                payment.user_subscription_id = (
                    invoice.user_subscription_id
                )
                payment.provider = invoice.provider
                payment.payment_type = payment_type
                payment.status = (
                    BillingPaymentStatus
                    .SUCCEEDED
                    .value
                )
                payment.currency = invoice.currency
                payment.amount = invoice.amount_paid
                payment.provider_charge_id = (
                    charge_id
                    or payment.provider_charge_id
                )
                payment.description = (
                    "Subscription payment"
                    if payment_type == "subscription"
                    else "Subscription renewal"
                )
                payment.paid_at = (
                    invoice.paid_at
                    or payment.paid_at
                    or utc_now()
                )
                payment.failure_code = None
                payment.failure_message = None
                payment.failed_at = None

            db.add(payment)
            db.flush()

            invoice.billing_payment_id = payment.id
            db.add(invoice)
            db.commit()
            db.refresh(invoice)
            db.refresh(payment)

        if invoice.user_subscription_id:
            subscription = (
                subscription_service
                .grant_period_tokens_if_needed(
                    db,
                    subscription_id=(
                        invoice.user_subscription_id
                    ),
                    reference_id=(
                        invoice.provider_invoice_id
                    ),
                )
            )

        return StripeWebhookResult(
            received=True,
            event_type=event_type,
            message=(
                "Paid invoice, subscription payment history "
                "and period tokens synchronized idempotently."
            ),
            metadata={
                "stripe_event_id": event_id,
                "billing_invoice_id": invoice.id,
                "billing_payment_id": (
                    payment.id
                    if payment
                    else invoice.billing_payment_id
                ),
                "user_subscription_id": (
                    subscription.id
                    if subscription
                    else invoice.user_subscription_id
                ),
            },
        )

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

    if MODEL_IMPORT not in source:
        anchor = "from app.common.time import utc_now\n"
        if anchor not in source:
            print(
                "ERROR: No se encontró el punto de importación esperado.",
                file=sys.stderr,
            )
            return 1
        source = source.replace(
            anchor,
            anchor + MODEL_IMPORT,
            1,
        )

    pattern = re.compile(
        r"    def _invoice_paid\(\n"
        r".*?"
        r"(?=    def _invoice_payment_failed\()",
        re.DOTALL,
    )
    match = pattern.search(source)
    if not match:
        print(
            "ERROR: No se encontró _invoice_paid con la estructura esperada.",
            file=sys.stderr,
        )
        return 1

    updated = (
        source[:match.start()]
        + NEW_INVOICE_PAID
        + source[match.end():]
    )

    backup = TARGET.with_suffix(".py.09S9.bak")
    if not backup.exists():
        shutil.copy2(TARGET, backup)

    TARGET.write_text(updated, encoding="utf-8")
    print("OK: app/services/billing_service.py actualizado.")
    print(f"Backup: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
