# FIX Backend — Periodicidad + webhook manual + simulación segura

BASE EXACTA
tryon_backend-main - 2026-08-07T180609.177.zip
(con la capa recurrente 05e ya aplicada en el código recibido)

ALCANCE
Este FIX NO reemplaza la capa recurrente anterior. Solo la completa con:
1. fin de ciclo calculado desde inicio + periodicidad;
2. endpoint/webhook manual idempotente;
3. simulación opt-in y dry-run.

PERIODICIDAD
Al crear una fuente ya NO se envía cycle_end.
Se configura:
- cycle_start
- recurrence: weekly / monthly / quarterly / yearly

Ejemplo Modal:
cycle_start = 2026-08-01
recurrence = monthly
=> el backend calcula current_cycle_end = 2026-09-01

El current_cycle_end sigue guardándose internamente para auditoría, pero el
administrador no tiene que calcularlo ni escribirlo.

MONTO DEL PRIMER CICLO VS. SIGUIENTES
Se conserva exactamente el comportamiento anterior:
- saldo real del ciclo actual puede ser USD 19.76;
- recurring_amount_usd puede ser USD 30;
- al siguiente ciclo se abre con USD 30;
- nada está hardcodeado a 30.

WEBHOOK MANUAL
Nuevo endpoint ADMIN autenticado:
POST /api/admin/finances/promotional-credits/recurring-sources/{source_id}/cycle-webhook

Llamada normal:
{
  "simulation": false
}

- Usa la fecha real del servidor.
- Invoca el MISMO ensure_current_cycles() del middleware/lazy guard.
- Es idempotente.
- Si el ciclo todavía está vigente, no mueve nada.
- Si ya venció, cierra/abre los ciclos que correspondan.
- El BackOffice usa este mismo endpoint con "Revisar ciclo ahora".
- Puede volver a llamarse en cualquier momento con autenticación admin.

SIMULACIÓN
Cada fuente tiene:
simulation_enabled = false por defecto

Solo si el administrador activa ese flag se permite:
{
  "simulation": true,
  "simulation_date": "2026-09-01"
}

La simulación:
- calcula cuántos ciclos se renovarían;
- muestra el período proyectado;
- NO cambia remaining_usd;
- NO cierra ciclos;
- NO crea ciclos;
- NO cambia dinero propio;
- NO cambia bolsas ni tokens.

Es deliberadamente dry-run para poder probar fechas futuras sin contaminar
la contabilidad real.

CAMBIO DE PERIODICIDAD
Se puede cambiar la periodicidad para ciclos futuros.
El período activo ya abierto NO se reescribe; conserva sus fechas históricas.
La nueva periodicidad empieza a usarse en el siguiente rollover.

BLINDAJE
NO modifica:
- fórmula de tokens;
- infraestructura/token;
- ganancias;
- descuentos;
- gastos operativos;
- FIFO comercial;
- snapshots;
- bolsas promocionales;
- prioridad recurrente -> dinero propio;
- vencimiento de créditos no acumulables;
- devoluciones tardías;
- Caja verde;
- Caja IA;
- Stripe;
- Modal / RunPod / Beam runtime;
- auto-desbloqueo.

MIGRACIÓN OBLIGATORIA
alembic upgrade head

HEAD ESPERADO
05f_promo_cycle_hook (head)

VALIDACIÓN REALIZADA
- python -m compileall: OK
- alembic heads: 05f_promo_cycle_hook (head)
- 83 contratos acumulados relevantes: PASSED
- 35 contratos del núcleo promocional/webhook: PASSED

COMANDOS
alembic upgrade head
alembic heads
python -m compileall -q app tests alembic/versions

python -m pytest -q `
  tests/test_promotional_cycle_webhook_periodicity_contract.py `
  tests/test_promotional_recurring_funding_cycle_contract.py `
  tests/test_promotional_credit_cashbox_contract.py `
  tests/test_promotional_admin_revoke_contract.py `
  tests/test_promotional_credit_no_regression_contract.py

GIT
git add .
git commit -m "feat: add promotional cycle periodicity webhook and safe simulation"
git push
