# 09S10 — Corrección `utc_now` en suscripciones

Corrige el error:

```text
NameError: name 'utc_now' is not defined
```

El error ocurría dentro de:

```text
app/services/subscription_service.py
grant_period_tokens_if_needed()
```

y provocaba que `invoice.paid` respondiera con HTTP 500.

## Aplicación

Descomprime este ZIP en la raíz de `tryon_backend` y ejecuta:

```powershell
.\apply_09S10.ps1
```

Después reinicia el backend.

## Reprocesar el evento fallido

Con Stripe CLI:

```powershell
stripe events resend evt_1TvgtcBmuIFKAYctta5i707i --webhook-endpoint we_YOUR_ENDPOINT_ID
```

Si estás usando `stripe listen --forward-to`, también puedes repetir la compra de prueba,
pero reenviar el mismo evento es preferible porque valida la idempotencia y evita otra compra.

No requiere migración de Alembic.
