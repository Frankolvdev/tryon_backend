# FIX Backend — Botón webhook visible + Simular +1 ciclo + blindaje reset

BASE
tryon_backend-main - 2026-08-07T182328.531.zip

CAMBIOS
1. Simulación simplificada:
   - ya NO recibe fecha;
   - siempre simula exactamente el SIGUIENTE ciclo configurado;
   - mensual => +1 mes;
   - semanal => +1 semana;
   - trimestral => +1 trimestre;
   - anual => +1 año;
   - nunca mueve dinero, tokens, bolsas ni ciclos reales.

2. Webhook/manual:
   POST /api/admin/finances/promotional-credits/recurring-sources/{source_id}/cycle-webhook
   body real: {"simulation": false}
   body simulación: {"simulation": true}

   Ambos llaman al mismo servicio de ciclos.
   La llamada real usa la fecha real del servidor y es idempotente.
   La simulación requiere que simulation_enabled esté activo en esa fuente.

3. Reset de datos de prueba:
   Se auditó generation_data_reset_service.py.
   YA incluía correctamente:
   - promotional_funding_cycles
   - promotional_funding_sources
   - promotional_credit_funds
   y los elimina en el orden correcto.

   Como este FIX no crea tablas nuevas, NO se cambia el motor del reset.
   Se agrega test de regresión para impedir que esas tablas se omitan en el futuro.
   Usuarios y avatares continúan preservados.

BLINDAJE
NO modifica:
- fórmulas financieras;
- token pricing;
- FIFO;
- snapshots;
- bolsas comerciales/promocionales;
- Caja verde;
- Caja IA;
- gastos operativos;
- Stripe;
- Modal/RunPod/Beam runtime;
- vencimientos;
- auto-desbloqueo.

MIGRACIÓN
NO hay nueva migración Alembic en este FIX.
La base debe seguir teniendo aplicada la migración 05f del ZIP anterior.

VALIDACIÓN REALIZADA
- python -m compileall: OK
- 38 pruebas promocionales/ciclos/reset: PASSED

PRUEBA RECOMENDADA
python -m pytest -q `
  tests/test_promotional_cycle_webhook_periodicity_contract.py `
  tests/test_generation_data_reset_promotional_cycles_contract.py `
  tests/test_promotional_recurring_funding_cycle_contract.py `
  tests/test_promotional_credit_cashbox_contract.py `
  tests/test_promotional_admin_revoke_contract.py `
  tests/test_promotional_credit_no_regression_contract.py

GIT
git add .
git commit -m "fix: expose promotional cycle webhook and simplify simulation"
git push
