# MegaZIP Backend — Capa recurrente para créditos promocionales

BASE EXACTA
tryon_backend-main - 2026-08-07T173801.173(1).zip

OBJETIVO
Añadir una capa de ciclos recurrentes a la Caja Promocional SIN reemplazar ni
reescribir el motor existente de tokens promocionales.

DOS FUENTES SEPARADAS

1. CRÉDITO RECURRENTE DEL PROVEEDOR
   Ejemplo Modal Starter.
   - Puede tener un saldo ACTUAL distinto al monto de los ciclos futuros.
   - Ejemplo real de configuración inicial:
       Nombre: Modal mensual
       Proveedor: modal
       Saldo real del ciclo actual: USD 19.76
       Inicio actual: 2026-08-01
       Fin actual: 2026-09-01
       Monto completo de siguientes ciclos: USD 30
   - Al llegar 2026-09-01, el sobrante del ciclo anterior NO se acumula.
   - El nuevo ciclo comienza con USD 30.
   - El monto no está hardcodeado: mañana puede ser USD 20, USD 40, etc.
   - Cambiar el monto durante un ciclo solo afecta los ciclos SIGUIENTES.

2. DINERO PROPIO
   - Usa exactamente los PromotionalCreditFund que ya existían.
   - Nunca se reinicia por ciclo.
   - No expira por esta capa.
   - Si el crédito recurrente se termina, el motor continúa con el dinero
     propio del mismo proveedor.
   - Todos los fondos existentes anteriores a esta migración se consideran
     dinero propio para NO reinterpretar ni alterar el histórico.

PRIORIDAD
Para un proveedor:
1. crédito recurrente vigente;
2. dinero propio.

No se modifica la forma en que se crean bolsas promocionales ni su snapshot.

RENOVACIÓN SIN WEBHOOK
Se implementa lazy/idempotent rollover mediante:
PromotionalFundingCycleService.ensure_current_cycles()

Se verifica antes de operaciones promocionales importantes:
- consultar Caja Promocional;
- agregar dinero propio;
- calcular fondos disponibles;
- otorgar tokens gratis;
- retirar tokens promocionales;
- devolver respaldo por vencimiento;
- devolver excedente después de una generación.

Por tanto NO requiere webhook ni que un proceso corra exactamente a las 00:00.
La primera operación posterior al cambio de ciclo actualiza el ciclo antes de
continuar.

Si más adelante existe scheduler/webhook, puede llamar al mismo método
idempotente sin crear una segunda lógica.

NO ACUMULABLE
Al cerrar un ciclo:
- el saldo libre sobrante se registra como expired_unused_usd;
- el fund anterior queda con remaining_usd=0;
- se abre el siguiente ciclo con recurring_amount_usd.

DEVOLUCIONES TARDÍAS
Si tokens respaldados por un ciclo viejo son retirados/vencen o generan
excedente DESPUÉS de que ese ciclo cerró:
- el importe se registra en returned_after_close_usd;
- NO resucita crédito vencido;
- NO se suma al nuevo ciclo;
- NO se convierte en dinero propio.

Esto evita acumular artificialmente beneficios mensuales vencidos.

BLINDAJE
No modifica:
- valor de token;
- fórmula de tokens por generación;
- infraestructura/token;
- ganancia;
- gastos operativos;
- FIFO comercial;
- snapshots comerciales;
- Stripe;
- Modal Runtime;
- RunPod Runtime;
- Beam Runtime;
- Caja verde;
- Caja IA;
- auto-desbloqueo;
- política de deudas promocionales;
- bolsas promocionales existentes;
- usuarios.

La protección contra devolver más respaldo del originalmente comprometido se
mantiene tanto para dinero propio como para ciclos cerrados.

RESET DE PRUEBAS
La función existente BORRAR ACTIVIDAD DE PRUEBAS ahora elimina también:
- promotional_funding_cycles
- promotional_funding_sources
antes de eliminar promotional_credit_funds.
Los usuarios siguen preservándose.

MIGRACIÓN OBLIGATORIA
alembic upgrade head

HEAD ESPERADO
05e_promo_cycles (head)

VALIDACIÓN
- python -m compileall: OK
- alembic heads: 05e_promo_cycles (head)
- 93 contratos financieros/promocionales acumulados: PASSED
- 11 contratos específicos de la capa recurrente: PASSED

No se pudo ejecutar integración DB SQLite en este entorno porque el proyecto
inicializa el dialecto PostgreSQL y psycopg2 no está instalado aquí. Los
contratos y compilación no requieren conexión.

APLICACIÓN
Extraer directamente sobre la raíz del backend.

COMANDOS
alembic upgrade head
alembic heads
python -m compileall -q app tests alembic/versions

python -m pytest -q `
  tests/test_promotional_recurring_funding_cycle_contract.py `
  tests/test_promotional_credit_cashbox_contract.py `
  tests/test_promotional_admin_revoke_contract.py `
  tests/test_promotional_credit_no_regression_contract.py `
  tests/test_generation_data_reset_financial_v4_contract.py

GIT
git add .
git commit -m "feat: add non-accumulating recurring promotional funding cycles"
git push
