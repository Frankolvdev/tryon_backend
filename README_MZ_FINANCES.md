# Backend — descuentos escalados y finanzas por generación

## Incluye
- Descuento comercial aplicado al porcentaje de la ganancia total contenida en todos los tokens del producto.
- Ganancia por token segura: menor `desired_profit_usd / estimated_tokens` entre módulos activos.
- Lotes de valor de tokens y consumo FIFO.
- Restauración de los mismos lotes en reembolsos de generación.
- Registro financiero por generación con ingreso reconocido, infraestructura y ganancia.
- Endpoint `GET /api/v1/admin/finances/generations`.
- Historial previo marcado como `partial` o `unavailable`; nunca se inventa ingreso.

## Aplicación
```powershell
alembic upgrade head
$env:PYTHONPATH = (Get-Location).Path
python -m compileall -q app tests
python -m pytest tests/test_generation_finance_contract.py -v
```
