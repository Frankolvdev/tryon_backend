# 09S11 — Historial de pagos de suscripción con Stripe moderno

Corrige la creación de movimientos de planes y suscripciones cuando Stripe no
incluye `invoice.payment_intent` directamente.

## Cambios

- Lee el PaymentIntent antiguo desde `invoice.payment_intent`.
- Lee el PaymentIntent moderno desde `invoice.payments.data`.
- Si Stripe no entrega PaymentIntent, crea el movimiento usando la factura.
- Usa `billing_invoice.billing_payment_id` para mantener idempotencia.
- Clasifica el primer pago como `subscription`.
- Clasifica renovaciones como `subscription_renewal`.
- Vincula pago, factura y suscripción.
- Permite reconstruir el movimiento reenviando `invoice.paid`.
- No requiere migración de Alembic.

## Aplicación

```powershell
.\apply_09S11.ps1
```

Reinicia el backend y reenvía el evento `invoice.paid` fallido desde Stripe.
