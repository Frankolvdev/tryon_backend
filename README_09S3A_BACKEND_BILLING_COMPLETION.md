# 09S3A Backend Billing Completion

## Included

- Subscription token grants recover the Stripe subscription from paid invoices even when `invoice.paid` arrives before `customer.subscription.created`.
- Stripe invoice subscription IDs support both the legacy `invoice.subscription` field and the newer `invoice.parent.subscription_details.subscription` shape.
- Token purchase refunds recover a missing PaymentIntent from the stored Checkout Session and persist the PaymentIntent/Charge IDs.
- The token checkout endpoint accepts either a package or a custom amount from 1 token upward.
- Custom token prices use the current backend commercial token value; no price is hardcoded.
- Internal renewal simulation command reuses the production idempotent token-grant logic and is disabled outside local/development/test environments.

## Database migration

```powershell
alembic upgrade head
```

## Existing package checkout

```json
{
  "token_package_id": 1,
  "success_url": "http://localhost:3003/billing/success",
  "cancel_url": "http://localhost:3003/billing/cancel"
}
```

## Custom token checkout

```json
{
  "tokens_amount": 1,
  "success_url": "http://localhost:3003/billing/success",
  "cancel_url": "http://localhost:3003/billing/cancel"
}
```

Send exactly one of `token_package_id` or `tokens_amount`.

## Simulate a subscription renewal

```powershell
python -m app.scripts.simulate_subscription_renewal --subscription-id 1
```

For an idempotency test, repeat a fixed reference:

```powershell
python -m app.scripts.simulate_subscription_renewal --subscription-id 1 --reference-id test-invoice-001
```
