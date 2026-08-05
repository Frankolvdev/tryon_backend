# FIX Backend — Conciliación desde Checkout Session

## Corrige
- Permite conciliar pagos aunque el webhook no haya copiado todavía el PaymentIntent.
- Si el pago es una compra de tokens, reutiliza el flujo idempotente de Stripe Checkout para actualizar pago, compra, tokens y bolsa.
- `can_reconcile` ahora es verdadero cuando existe PaymentIntent o Checkout Session.
- Un checkout abandonado se mantiene como intento después de verificarlo.

## Aplicación
```powershell
cd "F:\PROYECTOS PERSONALES\TRYON\backend"
.\.venv\Scripts\Activate.ps1
python -m compileall -q app
```
Reiniciar completamente el Backend. No requiere Alembic.
