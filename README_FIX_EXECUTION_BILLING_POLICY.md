# Política configurable de cobro por resultado

## Política predeterminada

- Completada: cobra infraestructura y aplica ganancia.
- Cancelada: cobra infraestructura y no aplica ganancia.
- Fallo de workflow/datos: cobra infraestructura y no aplica ganancia.
- Fallo interno/proveedor: no cobra infraestructura ni ganancia; devuelve la reserva completa.

La política se guarda en `system_settings` como JSON y se crea automáticamente si aún no existe. No requiere migración.

El desglose nuevo conserva `desired_profit_usd` y agrega `applied_profit_usd`, `profit_applied`, `infrastructure_charge_applied`, `billing_policy_key`, `failure_origin` y `raw_infrastructure_cost_usd`.

## Pruebas

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -m pytest tests/test_execution_billing_policy_contract.py -v
python -m pytest tests -v
```
