# 09S19 — Stripe invoice hardening

Ejecutar desde la raíz del backend después de descomprimir:

```powershell
.\APLICAR_09S19.ps1
```

Incluye:

- conserva `invoice.paid` e `invoice.payment_succeeded` apuntando al mismo handler;
- valida que el objeto recibido tenga `invoice.id` y estado `paid`;
- usa exclusivamente `invoice.id` como referencia idempotente para tokens;
- registra evento, factura, suscripción, usuario, importe y resultado;
- falla de forma visible si una factura de suscripción pagada no puede vincularse;
- no acredita tokens en `invoice.created` ni en `customer.subscription.updated`.

El aplicador es deliberadamente estricto: si el archivo local no coincide con la versión pública revisada, se detiene sin modificarlo.
