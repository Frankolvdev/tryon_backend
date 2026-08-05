# FIX — Resultado bloqueado y conciliación pendiente

Este parche corrige exclusivamente la presentación y los datos del caso de facturación pendiente.

## Qué corrige
- Conserva los tokens realmente cobrados inicialmente.
- Guarda `estimated_final_tokens` y los tokens pendientes cuando la conciliación no puede completarse.
- AppWeb muestra una tarjeta de resultado bloqueado, el costo estimado y el pendiente.
- AppWeb permite reintentar el desbloqueo con el endpoint existente.
- BackOffice diferencia tokens cobrados de tokens pendientes y muestra el estado bloqueado.
- No modifica Modal, Beam, RunPod, Stripe ni el FIFO de bolsas.

## Aplicación
Copiar el contenido de cada carpeta sobre la raíz del proyecto correspondiente:
- `backend/` sobre el backend.
- `appweb/` sobre el AppWeb.
- `backoffice/` sobre el BackOffice.
