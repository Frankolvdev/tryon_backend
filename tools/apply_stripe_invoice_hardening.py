from __future__ import annotations

from pathlib import Path

TARGET = Path('app/services/billing_service.py')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected exactly one match, found {count}.')
    return text.replace(old, new, 1)


def main() -> None:
    if not TARGET.exists():
        raise FileNotFoundError(f'Run this script from the backend root. Missing: {TARGET}')

    text = TARGET.read_text(encoding='utf-8')

    if 'logger = logging.getLogger(__name__)' not in text:
        text = replace_once(
            text,
            'from decimal import Decimal\n',
            'import logging\nfrom decimal import Decimal\n',
            'logging import',
        )
        anchor = 'from app.services.token_purchase_service import token_purchase_service\n'
        text = replace_once(
            text,
            anchor,
            anchor + '\nlogger = logging.getLogger(__name__)\n',
            'logger declaration',
        )

    old = '''    def _invoice_paid(\n        self,\n        db: Session,\n        *,\n        event_type: str,\n        event_id: str,\n        event_object: Any,\n    ) -> StripeWebhookResult:\n        invoice = billing_invoice_service.sync_invoice(\n            db,\n            stripe_invoice=event_object,\n        )\n        subscription = None\n        if not invoice.user_subscription_id:\n            provider_subscription_id = (\n                billing_invoice_service.provider_subscription_id(\n                    event_object\n                )\n            )\n            if provider_subscription_id:\n                subscription_service.retrieve_and_sync_provider_subscription(\n                    db,\n                    provider_subscription_id=provider_subscription_id,\n                )\n                invoice = billing_invoice_service.sync_invoice(\n                    db,\n                    stripe_invoice=event_object,\n                )\n\n        billing_reason = self._value(\n            event_object,\n            "billing_reason",\n        )\n        is_subscription_invoice = bool(\n            billing_reason\n            and str(billing_reason).startswith("subscription")\n        )\n        if is_subscription_invoice and not invoice.user_subscription_id:\n            raise ValueError(\n                "Paid subscription invoice could not be linked to "\n                "an internal subscription."\n            )\n\n        if invoice.user_subscription_id:\n            subscription = (\n                subscription_service.grant_period_tokens_if_needed(\n                    db,\n                    subscription_id=invoice.user_subscription_id,\n                    reference_id=invoice.provider_invoice_id,\n                )\n            )\n        return StripeWebhookResult(\n            received=True,\n            event_type=event_type,\n            message=(\n                "Paid invoice synchronized and subscription "\n                "tokens granted idempotently."\n            ),\n            metadata={\n                "stripe_event_id": event_id,\n                "billing_invoice_id": invoice.id,\n                "user_subscription_id": (\n                    subscription.id if subscription else None\n                ),\n            },\n        )\n'''

    new = '''    def _invoice_paid(\n        self,\n        db: Session,\n        *,\n        event_type: str,\n        event_id: str,\n        event_object: Any,\n    ) -> StripeWebhookResult:\n        provider_invoice_id = self._value(event_object, "id")\n        invoice_status = self._value(event_object, "status")\n        amount_paid = int(self._value(event_object, "amount_paid", 0) or 0)\n        billing_reason = self._value(event_object, "billing_reason")\n        provider_subscription_id = (\n            billing_invoice_service.provider_subscription_id(event_object)\n        )\n\n        logger.info(\n            "Stripe paid-invoice processing started: "\n            "event_id=%s event_type=%s invoice_id=%s status=%s "\n            "subscription_id=%s billing_reason=%s amount_paid=%s",\n            event_id,\n            event_type,\n            provider_invoice_id,\n            invoice_status,\n            provider_subscription_id,\n            billing_reason,\n            amount_paid,\n        )\n\n        if not provider_invoice_id:\n            raise ValueError("Stripe paid invoice is missing its invoice ID.")\n        if invoice_status != BillingInvoiceStatus.PAID.value:\n            raise ValueError(\n                "Stripe payment-success event did not contain a paid invoice: "\n                f"invoice_id={provider_invoice_id}, status={invoice_status}."\n            )\n\n        invoice = billing_invoice_service.sync_invoice(\n            db,\n            stripe_invoice=event_object,\n        )\n        subscription = None\n        if not invoice.user_subscription_id and provider_subscription_id:\n            subscription_service.retrieve_and_sync_provider_subscription(\n                db,\n                provider_subscription_id=provider_subscription_id,\n            )\n            invoice = billing_invoice_service.sync_invoice(\n                db,\n                stripe_invoice=event_object,\n            )\n\n        is_subscription_invoice = bool(\n            billing_reason\n            and str(billing_reason).startswith("subscription")\n        )\n        if is_subscription_invoice and not invoice.user_subscription_id:\n            logger.error(\n                "Stripe paid subscription invoice could not be linked: "\n                "event_id=%s invoice_id=%s subscription_id=%s",\n                event_id,\n                provider_invoice_id,\n                provider_subscription_id,\n            )\n            raise ValueError(\n                "Paid subscription invoice could not be linked to "\n                "an internal subscription."\n            )\n\n        if invoice.user_subscription_id:\n            # The immutable Stripe invoice ID is the idempotency reference.\n            # invoice.paid and invoice.payment_succeeded can therefore both\n            # call this method without granting the period twice.\n            subscription = (\n                subscription_service.grant_period_tokens_if_needed(\n                    db,\n                    subscription_id=invoice.user_subscription_id,\n                    reference_id=provider_invoice_id,\n                )\n            )\n\n        logger.info(\n            "Stripe paid-invoice processing completed: "\n            "event_id=%s invoice_id=%s billing_invoice_id=%s "\n            "user_id=%s user_subscription_id=%s token_reference=%s",\n            event_id,\n            provider_invoice_id,\n            invoice.id,\n            invoice.user_id,\n            invoice.user_subscription_id,\n            provider_invoice_id if subscription else None,\n        )\n\n        return StripeWebhookResult(\n            received=True,\n            event_type=event_type,\n            message=(\n                "Paid invoice synchronized and subscription "\n                "tokens granted idempotently."\n            ),\n            metadata={\n                "stripe_event_id": event_id,\n                "provider_invoice_id": provider_invoice_id,\n                "provider_subscription_id": provider_subscription_id,\n                "billing_invoice_id": invoice.id,\n                "billing_reason": billing_reason,\n                "amount_paid": amount_paid,\n                "user_id": invoice.user_id,\n                "user_subscription_id": (\n                    subscription.id if subscription else None\n                ),\n                "token_grant_reference": (\n                    provider_invoice_id if subscription else None\n                ),\n            },\n        )\n'''

    if old in text:
        text = replace_once(text, old, new, 'paid invoice handler')
    elif 'Stripe paid-invoice processing started:' in text:
        print('Stripe hardening is already applied; no changes needed.')
        return
    else:
        raise RuntimeError(
            'The current _invoice_paid implementation does not match the expected '
            'public repository version. No file was modified.'
        )

    required = [
        '"invoice.paid": self._invoice_paid',
        '"invoice.payment_succeeded": self._invoice_paid',
        'reference_id=provider_invoice_id',
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise RuntimeError(f'Post-patch validation failed. Missing: {missing}')

    compile(text, str(TARGET), 'exec')
    TARGET.write_text(text, encoding='utf-8', newline='\n')
    print(f'Updated and syntax-validated: {TARGET}')


if __name__ == '__main__':
    main()
