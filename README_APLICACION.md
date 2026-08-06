# MegaZIP Backend — Caja de infraestructura FIFO por bolsa

## Alcance
- Mantiene intacta la caja verde y sus retiros de utilidad.
- Crea movimientos de fondeo de infraestructura separados.
- Cada fondeo se asigna mediante FIFO a bolsas concretas.
- Un movimiento puede abarcar varias bolsas.
- Respeta la reserva congelada, descuentos, cupones, planes y snapshots de cada bolsa.
- Al vencer una bolsa, solo el efectivo todavía no transferido pasa a utilidad.
- La parte ya fondeada permanece como crédito libre en el proveedor.
- Registra movimientos, asignaciones por bolsa y liberaciones de crédito por proveedor.
- Bloquea reembolsos automáticos de bolsas cuya reserva ya fue fondeada.
- Usa bloqueos de fila para impedir dobles movimientos simultáneos.
- Incluye las tablas nuevas en el reinicio completo de datos de prueba.

## No modifica
- Fórmulas de precios o ganancias.
- FIFO de consumo de tokens.
- Snapshots históricos.
- Stripe, Modal, RunPod o Beam.
- Generaciones, bloqueo/desbloqueo o facturación normal.

## Aplicación
Extraer directamente sobre la raíz del backend.

## Migración obligatoria
alembic upgrade head

## Validación
python -m compileall -q app tests alembic/versions

pytest -q `
  tests/test_infrastructure_cashbox_fifo_contract.py `
  tests/test_token_bag_expiration_accounting_contract.py `
  tests/test_finance_cashbox_contract.py `
  tests/test_fifo_token_bag_pricing_v2_contract.py `
  tests/test_execution_billing_policy_contract.py `
  tests/test_commercial_snapshots_and_finance_contract.py

Validación realizada: 31 passed.
Alembic: 05a_infra_cashbox (head).
