# FIX — Resultado bloqueado por conciliación pendiente

## Alcance

Este parche modifica únicamente el backend. No modifica Modal, Beam, RunPod, Stripe, compras, bolsas FIFO, despliegues ni workflows.

Cuando una ejecución `completed` termina con un costo superior a la capacidad financiada por las bolsas:

- La ejecución sigue siendo `completed`.
- El archivo permanece almacenado.
- El usuario no recibe URLs del resultado.
- `result_locked=true`.
- `billing_access_status="payment_pending"`.
- Se conserva el cobro inicial.
- No se hace cobro parcial del faltante.
- El endpoint de conciliación puede reintentar el cobro después de comprar tokens.

## Instalación

Copiar el contenido de la carpeta `backend` sobre la raíz del backend, conservando las rutas.

## Variables de prueba

Agregar al archivo `.env` ubicado en la raíz del backend, junto a `app/`:

```env
TEST_FORCE_BILLING_OVERRUN=false
TEST_FORCE_BILLING_OVERRUN_MULTIPLIER=1.0
TEST_BILLING_USER_ID=
TEST_BILLING_EXECUTION_ID=
```

El modo de prueba está apagado por defecto y además se ignora cuando `APP_ENV=production` o `APP_ENV=prod`.

## Reproducción controlada

1. Averiguar el ID numérico del usuario con el que se hará la prueba.
2. Asegurarse de que el backend no use `APP_ENV=production`.
3. Configurar, por ejemplo:

```env
APP_ENV=development
TEST_FORCE_BILLING_OVERRUN=true
TEST_FORCE_BILLING_OVERRUN_MULTIPLIER=20
TEST_BILLING_USER_ID=1
TEST_BILLING_EXECUTION_ID=
```

4. Reiniciar completamente el backend.
5. Hacer una generación con ese usuario.
6. El proveedor se ejecutará a velocidad normal. Solo la facturación final simulará 20 veces el tiempo real.
7. Consultar el estado de la ejecución. Debe mostrar `status=completed`, `result_locked=true`, `billing_access_status=payment_pending` y sin URL de salida.
8. Comprar/acreditar tokens suficientes.
9. Reintentar la conciliación:

```http
POST /api/v1/generation-modules/executions/{execution_id}/settle-pending-billing
Authorization: Bearer <token_del_usuario>
```

10. Si las bolsas ya cubren el costo, el resultado cambia a `result_locked=false` y vuelve a entregar sus URLs.

## Limitar la prueba a una sola ejecución

Como el UUID se conoce después de crear la ejecución, puede hacerse así:

1. Dejar `TEST_FORCE_BILLING_OVERRUN=false` y crear una ejecución solo para conocer su UUID no sirve, porque esa ejecución ya arrancó.
2. La forma práctica es limitar por `TEST_BILLING_USER_ID`, ejecutar una sola generación y apagar inmediatamente el interruptor.
3. `TEST_BILLING_EXECUTION_ID` queda disponible para pruebas internas o reintentos dirigidos cuando el UUID se conozca de antemano.

## Apagar la prueba

Cambiar:

```env
TEST_FORCE_BILLING_OVERRUN=false
```

Reiniciar el backend. No dejar el interruptor activo durante pruebas de otros usuarios.

## Validación técnica

Ejecutar desde la raíz del backend:

```powershell
python -m compileall -q app
pytest -q
```

## Git

```powershell
git add .
git commit -m "feat: lock generation results when final billing is pending"
git push
```
