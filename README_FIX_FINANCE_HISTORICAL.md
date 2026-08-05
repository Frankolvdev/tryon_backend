# FIX Backend — Finanzas históricas y bolsas mixtas

## Corrige
- KeyError `infrastructure_capacity_from_tokens_usd` al refrescar registros financieros históricos/cancelados.
- Bolsas históricas que aparecían como no consumidas y reembolsables aunque un desglose financiero inmutable probara su uso.
- Detalle de generaciones por bolsa cuando las asignaciones antiguas quedaron totalmente revertidas.

## Seguridad
- La reconstrucción histórica es solo contable/visual.
- No vuelve a debitar tokens.
- No reduce saldos.
- No duplica movimientos.
- El flujo FIFO V2 para una o varias bolsas se conserva intacto.

## Aplicación
```powershell
cd "F:\PROYECTOS PERSONALES\TRYON\backend"
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
python -m compileall -q app tests
python -m pytest tests/test_finance_bag_historical_compatibility_contract.py tests/test_fifo_token_bag_pricing_v2_contract.py tests/test_finance_cashbox_contract.py -v
```

No requiere migración Alembic. Reinicia completamente el Backend.
