# FIX Backend - Generation Estimate Snapshot

Este fix conserva en cada ejecución la fotografía completa usada antes de cobrar y despachar el trabajo.

## Guarda desde el inicio

- `estimated_duration_seconds`
- `estimated_duration_source` (`initial` o `historical_average`)
- `estimated_billable_seconds`
- `estimated_infrastructure_cost_usd`
- `estimated_final_price_usd`
- `estimated_tokens_before_execution`
- proveedor, GPU, valor del token y regla de pricing dentro de `billing_breakdown`

## Al finalizar

El desglose real se combina con la fotografía inicial. No se borran los valores estimados al agregar:

- tiempo real del runtime
- costo real de infraestructura
- precio final
- tokens finales
- reembolso o débito adicional

## Aplicación

Descomprimir sobre la raíz del backend.

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -m pytest tests/test_generation_estimate_snapshot_contract.py -v
python -m pytest tests -v
```

## Git

```powershell
git add .
git commit -m "fix: persist complete pre-execution pricing estimate"
git push
```

No requiere migración: estos campos se persisten dentro del `snapshot_json` existente.
No modifica el runtime Modal, el pipeline, cancelaciones, snapshots, Beam ni RunPod.
No requiere volver a exportar o desplegar Modal.
