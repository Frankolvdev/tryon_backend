# FIX — Regla de precios primero, FIFO después

## Archivos modificados
- app/services/generation_module_runtime_service.py
- tests/test_fifo_token_bag_pricing_v2_contract.py
- tests/test_execution_billing_policy_contract.py

## Qué corrige
- La regla de precios vuelve a ser la única fuente para calcular la cantidad de tokens.
- FIFO solo selecciona las bolsas después de conocer la cantidad.
- Cupones, planes y descuentos solo afectan la ganancia atribuida a cada bolsa.
- Bloqueo y desbloqueo usan exactamente la misma cantidad de tokens.
- No se modifica Stripe, Modal, Beam, RunPod, creación de bolsas, ledger, asignación FIFO ni BackOffice.

## Validación
- python -m compileall -q app tests
- 18 contratos financieros relevantes aprobados.
