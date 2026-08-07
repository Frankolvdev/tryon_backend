# MegaZIP 4A — Backend — Caja de Gastos Operativos FINAL

BASE EXACTA
tryon_backend-main - 2026-08-07T134139.831.zip
(MegaZIP 1, 2 y 3 ya aplicados)

OBJETIVO
Activar el componente operativo que MegaZIP 3 dejó explícitamente separado,
sin modificar la fórmula que determina cuántos tokens cuesta una generación.

MODELO
Ejemplo actual:
  base económica token:      USD 0.110
  IA congelada:              USD 0.007
  ganancia normal:           USD 0.103
  operación configurada:     USD 0.002
  precio comercial nominal:  USD 0.112

Con descuento del 25% sobre ganancia:
  IA:                        USD 0.00700  (NO cambia)
  operación:                 USD 0.00200  (NO cambia)
  ganancia efectiva:         USD 0.07725
  cliente paga:              USD 0.08625

REGLA INVIOLABLE
La operación es un RECARGO COMERCIAL externo a token_value_usd.
token_charge_for_infrastructure() sigue sin leer:
- operational_reserve;
- commercial_sale_value.

Por tanto una generación mantiene exactamente la misma cantidad de tokens.

SNAPSHOTS
Cada bolsa nueva congela operational_reserve_per_token_usd.
Cambiarlo mañana NO recalcula ninguna bolsa anterior.
Bolsas históricas conservan su valor congelado (normalmente USD 0).

LIBERACIÓN A CAJA OPERATIVA
El fondo operativo se comporta de forma parecida a la ganancia, pero en una
caja completamente independiente:
- bolsa nueva/reembolsable: operación BLOQUEADA;
- primer consumo: la bolsa deja de ser reembolsable y se libera el componente
  operativo respaldado por los tokens que realmente pertenecían a la bolsa;
- bolsa nunca usada que vence: se libera el componente operativo de los tokens
  vencidos;
- bolsa reembolsada: no libera fondo operativo;
- bolsa promocional: jamás aporta a Caja Operativa.

Un reembolso parcial previo al primer uso tampoco puede liberar dinero
correspondiente a los tokens devueltos.

GASTOS / RETIROS OPERATIVOS
Nueva tabla operational_expenses.
Permite registrar de forma independiente:
- hosting;
- correo;
- dominios;
- storage;
- software;
- contabilidad;
- otros.

Cada movimiento soporta importe, categoría, beneficiario, concepto, método,
comprobante/notas y fecha.

No permite gastar más de lo que la Caja Operativa tiene liberado. La operación
se serializa con bloqueo de fila para evitar doble gasto simultáneo.

NO SE MEZCLA CON
- Caja verde / utilidad;
- retiros de utilidad;
- Caja IA;
- fondeos Modal/RunPod/Beam;
- créditos promocionales;
- pérdidas pendientes.

PRECIOS Y DESCUENTOS
pricing_service.price_for_tokens() usa:
    commercial_sale_value = token_value_usd + operational_reserve

financial_protection_service continúa descontando exclusivamente:
    safe_profit_per_token * discount_percent

Así cupones, paquetes y planes nunca descuentan IA ni operación.

IMPORTANTE AL CAMBIAR EL RECARGO
Después de guardar el nuevo fondo operativo por token en BackOffice, usar
"Recalcular catálogo" para actualizar paquetes y planes locales.
Los planes recurrentes que ya están sincronizados con Stripe conservan la
política existente del proyecto: deben sincronizarse con Stripe para que el
nuevo precio aplique al siguiente periodo, sin tocar el periodo ya pagado.

MIGRACIÓN OBLIGATORIA
alembic upgrade head

Head esperado:
05c_operational_cashbox (head)

VALIDACIÓN REALIZADA
- python -m compileall: OK
- alembic heads: 05c_operational_cashbox (head)
- 75 contratos acumulados directamente relacionados: PASSED
- batería financiera amplia: 90 PASSED / 5 FAILED
- los mismos 5 fallos históricos ya existían antes de MegaZIP 4 y no fueron
  modificados artificialmente.

PRUEBA RECOMENDADA
python -m pytest -q `
  tests/test_operational_cashbox_contract.py `
  tests/test_operational_snapshot_discount_contract.py `
  tests/test_financial_components_v3_contract.py `
  tests/test_token_financial_snapshot_v3_values.py `
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

Resultado esperado para ese conjunto: 75 passed.
