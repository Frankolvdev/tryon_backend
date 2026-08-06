# FIX — Reserva fija de IA en bolsas nuevas

## Alcance
- Conserva intactos FIFO, cobro de generaciones, snapshots históricos, Stripe y proveedores.
- Las bolsas comerciales nuevas congelan la reserva de IA desde la regla base:
  `token_value_usd - normal_profit_per_token_usd`.
- Cupones, planes y promociones reducen la ganancia; no reducen la reserva de IA.
- Si un periodo histórico ya pagado vino con precio menor al esperado, se conserva la reserva de IA y se ajusta hacia abajo la ganancia real de esa bolsa.
- Créditos antiguos o no comerciales sin snapshot completo conservan la fórmula de compatibilidad anterior.
- Las bolsas históricas existentes no se modifican automáticamente.

## Archivos
- app/services/token_value_ledger_service.py
- tests/test_token_lot_infrastructure_protection_contract.py

## Validación
- `python -m compileall -q app tests`
- 15 contratos principales pasaron.
- 9 de 10 contratos adicionales pasaron. La prueba histórica `test_cashbox_uses_historical_financial_evidence_when_net_allocations_are_zero` ya falla en el ZIP base porque espera un método `_historical_bag_usage` que no existe; no se modificó Caja para ocultar ese problema ajeno.
