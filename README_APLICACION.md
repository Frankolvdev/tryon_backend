# MegaZIP 2A — Backend — Créditos promocionales respaldados

BASE EXACTA:
tryon_backend-main - 2026-08-07T123540.522.zip
(con MegaZIP 1 ya aplicado por el usuario)

OBJETIVO
Añadir una caja separada de créditos promocionales/gratuitos sin alterar:
- pricing comercial;
- cantidad de tokens por generación;
- FIFO comercial;
- snapshots comerciales;
- Caja verde;
- Caja IA comercial;
- Stripe;
- Modal / RunPod / Beam;
- bloqueo/desbloqueo existente.

MODELO PROMOCIONAL
1. Un fondo promocional se registra en USD y tiene proveedor:
   modal / runpod / beam / general.
2. Los tokens promocionales tienen:
   - cliente pagó = USD 0;
   - ganancia empresa = USD 0;
   - provider funding trazable;
   - snapshot propio e inmutable.
3. Los tokens promocionales sirven para GENERACIONES NUEVAS.
4. Por defecto NO sirven para deudas/generaciones bloqueadas anteriores.
5. El switch `promotional_allow_pending_settlement` permite cambiar
   explícitamente esa política.
6. Los créditos Modal solo financian ejecuciones Modal; RunPod solo RunPod;
   Beam solo Beam; General puede financiar cualquier proveedor.
7. El bono de registro reutiliza `free_signup_tokens`, pero solo entrega tokens
   si `promotional_signup_enabled=true` y existe respaldo real.
8. Si se configuran 12 tokens y solo quedan 4 financiables, signup recibe 4.
9. Una asignación manual es exacta: si no alcanza el fondo, no crea tokens.
10. Al vencer tokens promocionales, su respaldo NO pasa a Caja verde:
    regresa al mismo fondo promocional.

PROTECCIÓN IMPORTANTE
Un token promocional contiene CERO ganancia. Por eso al entregarlo se reserva
temporalmente del fondo promocional el valor comercial completo del token
(p.ej. USD 0.11), no solamente los USD 0.007 de capacidad IA de una generación
completed.

Esto NO cambia la fórmula comercial ni el precio en tokens de una generación.
El snapshot conserva por separado:
- `infrastructure_capacity_per_token_usd`: reserva normal usada por la regla
  de generación (p.ej. USD 0.007);
- `promotional_funding_per_token_usd`: respaldo promocional temporal completo
  (p.ej. USD 0.11).

Al terminar una ejecución, el costo real proporcional consumido por esos tokens
permanece gastado y TODO respaldo promocional no utilizado vuelve a su fondo.
Esto protege también cancelaciones/fallos, donde la política puede no aplicar
ganancia y un token puede cubrir una fracción de infraestructura distinta.

VENCIMIENTO
Este MegaZIP corrige además una inconsistencia preexistente necesaria para que
los créditos promocionales sean seguros: al expirar una bolsa, ahora también se
restan esos tokens del `User.token_balance` en la misma transacción. Antes podía
ponerse el lote en cero pero dejar saldo gastable que luego reaparecía como
legacy/untraced.

ENTORNO DE PRUEBAS
Se agrega `pytest.ini`:
[pytest]
pythonpath = .
testpaths = tests

Aun así se recomienda ejecutar `python -m pytest`.

MIGRACIÓN OBLIGATORIA
alembic upgrade head

Head esperado:
05b_promo_credits (head)

VALIDACIÓN REALIZADA
- python compileall: OK
- Alembic head: 05b_promo_credits
- 53 contratos directamente relacionados: PASSED
- Batería financiera ampliada: 65 PASSED
- 2 contratos históricos fallan también en el ZIP base SIN MegaZIP 2:
  * test_finance_bag_historical_compatibility_contract.py
  * test_generation_finance_contract.py
  Se confirmó contra una extracción limpia y NO se maquillaron.

PRUEBA RECOMENDADA
python -m pytest -q \
  tests/test_promotional_credit_cashbox_contract.py \
  tests/test_promotional_credit_no_regression_contract.py \
  tests/test_pending_generation_auto_settlement_contract.py \
  tests/test_pending_recovery_cashbox_contract.py \
  tests/test_infrastructure_cashbox_fifo_contract.py \
  tests/test_token_bag_expiration_accounting_contract.py \
  tests/test_finance_cashbox_contract.py \
  tests/test_fifo_token_bag_pricing_v2_contract.py \
  tests/test_execution_billing_policy_contract.py \
  tests/test_commercial_snapshots_and_finance_contract.py
