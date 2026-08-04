# MegaZIP 1 — Backend Financial Protection Engine

## Alcance

Este ZIP es incremental y debe descomprimirse sobre la raíz del backend actualizado.

Implementa:

- Motor central de protección financiera.
- Máximo global protegido de descuento.
- Máximo seguro calculado, holgura y módulo/regla limitantes.
- Buffer conservador de duración configurable.
- Bloqueo de cambios peligrosos en reglas de pricing, precios GPU y módulos activos/proveedor.
- Descuentos protegidos para planes y paquetes de tokens.
- Cupones limitados a paquetes de tokens y compra libre de tokens.
- Eliminación de promociones genéricas de Stripe en suscripciones y compras de tokens.
- Aplicación de cupones por código desde el backend, con snapshot financiero inmutable en la compra.
- Protección contra acumulación de descuento de paquete + cupón por encima del máximo global.
- Migración de paquetes existentes y normalización de cupones antiguos que aplicaban a planes/all.

## Endpoints nuevos

- `GET /api/v1/admin/financial-protection`
- `PATCH /api/v1/admin/financial-protection`

Payload de configuración:

```json
{
  "protected_discount_percent": 25,
  "duration_safety_buffer_percent": 10
}
```

## Migración

```powershell
alembic upgrade head
```

La migración agrega a `token_packages`:

- `requested_discount_percent`
- `effective_discount_percent`
- `nominal_price_cents`

También normaliza cupones antiguos con alcance `all` o `plans` para que apliquen solamente a `token_packages`.

## Validación

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -m compileall -q app tests
python -m pytest tests/test_financial_protection_engine_contract.py -v
python -m pytest tests/test_generation_estimate_snapshot_contract.py tests/test_execution_billing_policy_contract.py tests/test_generation_configuration_readiness_relation_contract.py -v
```

## Comportamiento importante

- Los cupones ya no se aplican a planes.
- Stripe Checkout no acepta códigos promocionales genéricos para planes ni tokens.
- Las compras de tokens usan `coupon_code` explícito en el request.
- El backend calcula y congela el descuento efectivo antes de crear Checkout.
- Si un descuento solicitado supera el máximo global protegido, la operación se rechaza.
- Si un cambio de GPU, regla o módulo reduce el máximo seguro por debajo del compromiso global, el cambio se rechaza antes del commit.

## No modifica

- Runtime Builder.
- Modal, Beam o RunPod.
- ComfyUI embebido.
- Snapshots GPU/CPU.
- Pipeline de generación.
- Cancelaciones.
- Recuperación tras reinicio.
- Telemetría y billing por ejecución.
