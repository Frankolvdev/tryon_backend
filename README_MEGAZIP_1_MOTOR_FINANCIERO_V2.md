# MegaZIP 1 — Motor Financiero V2 por Bolsas FIFO

## Alcance

Este paquete cambia la reserva inicial y la conciliación final de tokens para utilizar las condiciones económicas congeladas de las bolsas FIFO reales del usuario.

Antes, la cantidad de tokens se calculaba con el valor global y la ganancia de la Pricing Rule vigente; después Finanzas repartía esos tokens usando bolsas históricas. Eso podía provocar que la cantidad cobrada no coincidiera con la capacidad real de infraestructura de las bolsas consumidas.

Ahora:

1. Se consultan primero las bolsas FIFO.
2. Cada bolsa aporta su valor efectivo pagado por token.
3. Se resta su ganancia efectiva congelada cuando la política aplica ganancia.
4. Se calcula cuántos tokens de cada bolsa cubren el costo estimado o real.
5. La conciliación existente debita o devuelve la diferencia.
6. El desglose conserva qué bolsas y capacidades justificaron el cobro.

## Snapshots nuevos

Las bolsas nuevas guardan:

- `financial_snapshot_version = 2`
- `effective_paid_token_value_usd`
- `infrastructure_capacity_per_token_usd`

Las bolsas históricas se derivan de sus campos existentes. Solo los saldos realmente antiguos sin snapshot usan un fallback marcado como trazabilidad parcial.

## No incluye todavía

- Caja registradora.
- Retiros.
- Caducidad.
- Activación de utilidad por primer consumo.
- Reembolsos y conciliación Stripe por bolsa.
- Políticas legales.

Esos módulos se construirán sobre esta base en los MegaZIPs siguientes.

## Aplicación

Descomprimir sobre la raíz del Backend.

```powershell
cd "F:\PROYECTOS PERSONALES\TRYON\backend"

.\.venv\Scripts\Activate.ps1

$env:PYTHONPATH = (Get-Location).Path

python -m compileall -q app tests

python -m pytest tests/test_fifo_token_bag_pricing_v2_contract.py tests/test_finance_accuracy_contract.py tests/test_cancelled_finance_policy_contract.py -v
```

No requiere migración Alembic.

Reiniciar completamente el Backend después de aplicar.

## Git

```powershell
git add .
git commit -m "feat: calculate generation charges from FIFO token bag snapshots"
git push
```
