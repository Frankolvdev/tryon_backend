# MegaZIP 3A — Backend — Blindaje financiero V3

BASE EXACTA
tryon_backend-main - 2026-08-07T130411.041.zip
(MegaZIP 1 y MegaZIP 2 ya aplicados por el usuario)

OBJETIVO
Centralizar los componentes económicos de cada token antes de introducir la
Caja de Gastos Operativos del MegaZIP 4. Este MegaZIP NO activa todavía ningún
recargo operativo.

ARQUITECTURA V3
Cada bolsa nueva congela explícitamente:
- token_value_usd: base económica que usa la generación;
- infrastructure_capacity_per_token_usd;
- operational_reserve_per_token_usd (0 por ahora);
- normal_profit_per_token_usd;
- effective_profit_per_token_usd;
- profit_discount_percent;
- financial_economics_schema = explicit_components_v3.

REGLA CENTRAL
La infraestructura de una bolsa nueva NO se reconstruye como:
    precio_pagado - ganancia
Los consumidores leen el componente congelado.

La única compatibilidad "paid - profit" que queda está encapsulada dentro de
token_financial_snapshot_service y se usa exclusivamente como fallback para
bolsas genuinamente antiguas que no tienen componentes congelados.

GENERACIONES
El número de tokens continúa calculándose solamente desde:
    token_value_usd - ganancia protegida de la regla
El futuro componente operativo NO participa en esta fórmula.

PRECIO COMERCIAL PREPARADO PARA MEGAZIP 4
Se separan:
- token_value_usd: base de generación;
- operational_reserve_per_token_usd: 0 actualmente;
- commercial_sale_value_per_token_usd: base + operación.

price_for_tokens() usa commercial_sale_value_per_token_usd. Como operación
todavía vale 0, este MegaZIP no cambia ningún precio actual.

DESCUENTOS
Siguen reduciendo únicamente la ganancia. No modifican infraestructura ni
el futuro componente operativo.

SNAPSHOTS HISTÓRICOS
No se migran ni recalculan. V2 y legacy continúan siendo legibles.
Las bolsas nuevas pasan a financial_snapshot_version=3.

PROMOCIONALES
Mantienen:
- cliente pagó = 0;
- ganancia = 0;
- respaldo promocional propio;
- capacidad IA congelada independiente;
- operational_reserve = 0.
No se modifica su política de deudas del MegaZIP 2.

SIMULADOR
Queda preparado para separar la reserva operativa del redondeo y de la
ganancia. Con operación=0 el resultado actual es idéntico.

NO MODIFICA
- FIFO de consumo;
- generación runtime;
- generation_module_billing_service;
- Stripe;
- Modal;
- RunPod;
- Beam;
- Caja verde;
- Caja IA/fondeos;
- pérdidas pendientes/auto-desbloqueo;
- vencimientos;
- migraciones de base de datos.

MIGRACIÓN
NO hay migración Alembic en MegaZIP 3.

VALIDACIÓN REALIZADA
- python -m compileall: OK
- 68 contratos directamente relacionados: PASSED
- Suite amplia ejecutable en este entorno:
    123 PASSED
    5 FAILED
  Los mismos 5 fallos existen en el ZIP BASE sin MegaZIP 3:
  * test_financial_limiting_rule_contract.py
  * test_finance_bag_historical_compatibility_contract.py (su segundo contrato)
  * test_financial_protection_engine_contract.py
  * test_financial_limiting_rule_all_active_contract.py
  * test_generation_finance_contract.py
- 5 pruebas Runtime Builder adicionales no pudieron coleccionarse en este
  entorno por falta de psycopg2; no fueron modificadas por este MegaZIP.

PRUEBA RECOMENDADA
python -m pytest -q `
  tests/test_token_financial_snapshot_v3_values.py `
  tests/test_financial_components_v3_contract.py `
  tests/test_fifo_token_bag_pricing_v2_contract.py `
  tests/test_token_lot_infrastructure_protection_contract.py `
  tests/test_promotional_credit_cashbox_contract.py `
  tests/test_promotional_credit_no_regression_contract.py `
  tests/test_pending_generation_auto_settlement_contract.py `
  tests/test_pending_recovery_cashbox_contract.py `
  tests/test_infrastructure_cashbox_fifo_contract.py `
  tests/test_token_bag_expiration_accounting_contract.py `
  tests/test_finance_cashbox_contract.py `
  tests/test_execution_billing_policy_contract.py `
  tests/test_commercial_snapshots_and_finance_contract.py

Resultado validado para ese conjunto: 68 passed.
