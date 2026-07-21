# 09S9 — Historial de pagos de suscripción

Este hotfix corrige el flujo `invoice.paid` del backend.

## Corrige

- Crea o actualiza idempotentemente un `BillingPayment`.
- Registra `subscription` en el primer cobro.
- Registra `subscription_renewal` en renovaciones.
- Vincula la factura con `billing_payment_id`.
- Conserva la acreditación idempotente de tokens.
- Evita duplicados usando el `PaymentIntent` único de Stripe.

## Aplicación

Descomprime el ZIP en la raíz de `tryon_backend` y ejecuta:

```powershell
.\apply_09S9.ps1
```

El script crea una copia:

`app/services/billing_service.py.09S9.bak`

No requiere migración de Alembic porque utiliza columnas existentes.
