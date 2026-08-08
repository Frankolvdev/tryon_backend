# FIX Backend — Excedente promocional cuando una generación usa la misma bolsa más de una vez

BASE EXACTA
tryon_backend-main - 2026-08-07T185640.579.zip

CAUSA REAL DEL ERROR
Una generación puede crear más de una TokenConsumptionAllocation contra la MISMA
bolsa promocional. Esto es válido y ocurre, por ejemplo, cuando:
1. se cobran los tokens estimados al iniciar;
2. al finalizar el costo real requiere tokens adicionales;
3. esos tokens adicionales todavía salen de la misma bolsa/promotional grant.

El settlement promocional anterior recorría cada allocation por separado.
Por eso intentaba crear dos PromotionalCreditReturn con:
- mismo grant_id
- reason = execution_surplus
- mismo execution_id

La base de datos bloqueó correctamente el segundo INSERT mediante:
uq_promo_return_idempotency.

NO SE QUITA NI SE RELAJA ESA RESTRICCIÓN UNIQUE.

CORRECCIÓN
settle_execution_surplus() ahora:
1. conserva las allocations tal como existen;
2. calcula net allocations como antes;
3. agrupa únicamente las allocations promocionales por lot/grant;
4. suma sus tokens netos;
5. calcula el mismo sponsored value y actual provider share sobre el total agregado;
6. crea UNA sola devolución monetaria por grant + ejecución;
7. mantiene FOR UPDATE y consulta de idempotencia;
8. hace flush del registro idempotente antes de pasar al siguiente grant.

Matemáticamente no cambia el importe:
sum(reserve*n_i - infra*n_i/total)
=
reserve*sum(n_i) - infra*sum(n_i)/total

Por tanto no cambia:
- cantidad de tokens;
- FIFO;
- allocations;
- costo real;
- reserve_per_token;
- descuentos;
- ganancia;
- gastos operativos;
- bolsas;
- proveedor;
- ciclos recurrentes.

RESET DE DATOS DE PRUEBA — AUDITADO
NO fue la causa del error.

El reset actual YA elimina, en orden correcto:
1. promotional_credit_returns
2. promotional_token_grants
3. promotional_funding_cycles
4. promotional_funding_sources
5. promotional_credit_funds

También:
- elimina token_consumption_allocations;
- elimina token_value_lots;
- pone user.token_balance en 0;
- conserva users;
- conserva avatar_file_id.

No se modificó production code del reset porque ya estaba correcto.
El nuevo contrato de regresión verifica ese orden y esas protecciones.

POR QUÉ EL LOG PRUEBA QUE ERA LA MISMA FINALIZACIÓN
El SQL fallido contenía DOS filas pendientes en el mismo INSERT:
- grant_id=1, reason=execution_surplus, misma execution_id, amount=0.725466
- grant_id=1, reason=execution_surplus, misma execution_id, amount=0.310914

Ambas cantidades equivalen al mismo surplus por token:
0.725466 / 7 = 0.103638
0.310914 / 3 = 0.103638

Eso encaja con 7 tokens de un cobro y 3 tokens de un ajuste, ambos pertenecientes
al mismo grant promocional.

VALIDACIÓN
- python -m compileall: OK
- 47 pruebas de promociones/ciclos/reset: PASSED
- batería financiera amplia del FIX: 77 PASSED / 5 FAILED
- exactamente los mismos 5 fallos aparecen en el ZIP BASE sin este FIX;
  por tanto no son regresiones introducidas por esta corrección.

SIN MIGRACIÓN
No ejecutar alembic por este FIX.

PRUEBA RECOMENDADA
python -m pytest -q `
  tests/test_promotional_execution_surplus_idempotency_contract.py `
  tests/test_promotional_credit_cashbox_contract.py `
  tests/test_promotional_recurring_funding_cycle_contract.py `
  tests/test_promotional_cycle_webhook_periodicity_contract.py `
  tests/test_promotional_admin_revoke_contract.py `
  tests/test_promotional_credit_no_regression_contract.py `
  tests/test_generation_data_reset_financial_v4_contract.py `
  tests/test_generation_data_reset_promotional_cycles_contract.py

GIT
git add .
git commit -m "fix: aggregate promotional execution surplus by grant"
git push
