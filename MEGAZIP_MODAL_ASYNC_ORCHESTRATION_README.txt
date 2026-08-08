MEGAZIP — MODAL ASYNC ORCHESTRATION / REDIS QUEUE SCALING
Fecha: 2026-08-08
Base: backend limpio entregado por el usuario (NO contiene el ZIP descartado anterior)

OBJETIVO
=======
Mantener intacta la experiencia y la lógica existente de generación, billing,
FIFO, tokens, almacenamiento, cancelación, errores y estados; cambiar únicamente
la forma interna en que Modal se despacha y se supervisa para soportar miles de
trabajos sin crear un thread Redis / BLPOP por cada contenedor remoto posible.

REGLA ARQUITECTÓNICA NUEVA
=========================
ANTES:
  modal_max_containers * modal_concurrency
  = número de workers locales
  = número de BLPOP Redis bloqueantes

Ejemplo: 100 * 1 = 100 conexiones Redis -> agotaba pool Python de 100.

AHORA:
  modal_max_containers * modal_concurrency
  = capacidad REAL remota de Modal.

  GENERATION_MODAL_QUEUE_DISPATCHERS
  = pequeño pool local que solamente saca jobs de Redis y hace spawn().

  Modal FunctionCall.get.aio()
  = supervisor asíncrono del resultado; no crea un thread Python por ejecución
    y no introduce polling fijo de 2/5 segundos para detectar el resultado.

Ejemplos:
  1000 containers * 1 concurrency = 1000 ejecuciones Modal activas posibles.
  1000 containers * 2 concurrency = 2000 ejecuciones Modal activas posibles.

El backend NO crea 1000/2000 BLPOP ni 1000/2000 threads de espera.

FLUJO
=====
Usuario -> Backend -> PostgreSQL -> Redis durable -> Modal dispatchers

Si hay capacidad remota:
Redis -> spawn() -> persiste provider_job_id -> async supervisor -> Modal

Si NO hay capacidad:
el job permanece en Redis; NO se saca a una cola local ilimitada.

Cuando Modal termina:
get.aio() despierta en cuanto el SDK entrega el resultado -> se libera el slot
remoto -> finalización local limitada -> MISMA lógica existente de outputs,
storage, métricas, dynamic billing, deuda/result_locked y estado final.

RECUPERACIÓN TRAS REINICIO
==========================
- Jobs queued: permanecen/reingresan a Redis con dedupe existente.
- Jobs Modal running con provider_job_id: NO se reencolan y NO se vuelven a
  crear. Se restaura el mismo FunctionCall ID y se reanuda su supervisión.
- Si Modal terminó mientras el backend estaba apagado, get.aio() obtiene el
  resultado ya disponible y ejecuta la finalización normal.
- Recuperación se registra ANTES de arrancar dispatchers nuevos, evitando que
  el reinicio sobrepase la capacidad configurada.
- La reconexión de miles de FunctionCalls se hace en lotes controlados (50 por
  defecto, pausa de 250 ms) para evitar una estampida al control plane.
- Un reconciliador de seguridad revisa cada 30 s ejecuciones running que hayan
  quedado sin supervisor. NO es el mecanismo normal de entrega de resultados.

RESULTADO INMEDIATO
===================
El resultado normal NO se consulta cada 5 segundos.
Se usa await FunctionCall.get.aio(timeout=...), por lo que una ejecución puede
ser detectada en cuanto Modal entrega el resultado.

El heartbeat que mantiene RUNNING/progress en AppWeb/BackOffice solo consulta
el task LOCAL del supervisor; NO hace requests de polling a Modal y NO agrega
latencia al resultado.

BACKPRESSURE / NO SATURACIÓN
============================
- Redis mantiene trabajos pendientes.
- Solo 16 dispatchers Modal por defecto consumen BLPOP.
- PostgreSQL NO queda abierto durante toda la ejecución remota Modal.
- Resultados pesados se finalizan con 16 workers locales por defecto.
- Miles de waits remotos viven como coroutines async, no como miles de threads.
- Después de un reinicio, recuperación se hace por lotes.

REDIS
=====
Se usa BlockingConnectionPool para que un pico local espere por una conexión
libre en lugar de caer inmediatamente en "Too many connections".

Defaults:
  REDIS_MAX_CONNECTIONS=256
  REDIS_POOL_WAIT_SECONDS=5

Estos valores NO crecen con modal_max_containers.

CONFIG OPCIONAL (.env)
======================
NO es obligatorio agregar nada. Existen defaults seguros.

Opcionalmente:
  REDIS_MAX_CONNECTIONS=256
  REDIS_POOL_WAIT_SECONDS=5
  GENERATION_MODAL_QUEUE_DISPATCHERS=16
  GENERATION_MODAL_FINALIZER_WORKERS=16
  GENERATION_MODAL_FINALIZATION_RETRIES=5
  GENERATION_MODAL_RECONCILE_SECONDS=30
  GENERATION_MODAL_RECOVERY_BATCH_SIZE=50
  GENERATION_MODAL_RECOVERY_BATCH_DELAY_MS=250

IMPORTANTE:
GENERATION_MODAL_QUEUE_DISPATCHERS NO es la cantidad máxima de generaciones.
El máximo remoto sigue siendo:
  modal_max_containers * modal_concurrency

COMPATIBILIDAD / BLINDAJE
=========================
NO se modificaron:
- runtime_builder_service.py (runtime/deploy Modal)
- runpod_serverless_adapter_service.py
- runpod_client_service.py
- beam_serverless_adapter_service.py
- generation_module_billing_service.py
- generation_finance_service.py
- token_value_ledger_service.py
- pricing/FIFO/promociones
- Stripe
- storage general
- workflows/módulos
- lógica Modal cancel_call 50s + 20s

El método execute_pipeline() anterior se conserva como compatibilidad/legacy.
El nuevo orquestador Modal usa submit_pipeline() + await_result_async() y la
nueva finalización supervisada, sin reemplazar el contrato de generación.

ARCHIVOS MODIFICADOS
====================
app/core/config.py
app/core/redis_client.py
app/schemas/ai_engine_settings.py
app/services/generation_job_orchestrator_service.py
app/services/generation_module_runtime_service.py
app/services/modal_pipeline_adapter_service.py

PRUEBAS AGREGADAS
=================
tests/test_modal_async_orchestration_scaling_contract.py
tests/test_modal_async_wait_runtime.py

VALIDACIÓN REALIZADA EN LA ENTREGA
==================================
python -m compileall -q app
  OK (solo warnings preexistentes de escapes en archivos ajenos al fix)

pytest -q \
  tests/test_modal_async_wait_runtime.py \
  tests/test_modal_async_orchestration_scaling_contract.py \
  tests/test_megazip_dynamic_pricing_resilience_contract.py \
  tests/test_modal_runtime_exact_billing_contract.py

Resultado:
  19 passed

La prueba live contra TU PostgreSQL/Redis/Modal debe realizarse después de
aplicar, porque las credenciales/servicios live no existen dentro del entorno
de construcción del MegaZIP.

PRIMERA PRUEBA RECOMENDADA
==========================
1. Copiar los archivos del MegaZIP sobre el backend.
2. Ejecutar:
   python -m compileall -q app

3. Ejecutar:
   pytest -q tests/test_modal_async_wait_runtime.py tests/test_modal_async_orchestration_scaling_contract.py tests/test_megazip_dynamic_pricing_resilience_contract.py tests/test_modal_runtime_exact_billing_contract.py

4. Iniciar:
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8001

5. El arranque debe incluir un log parecido a:
   Generation orchestrator started: modal_capacity=100 modal_queue_dispatchers=16 ...

   Con max_containers=1000, concurrency=1:
   modal_capacity=1000 modal_queue_dispatchers=16

6. Verificar Redis mientras backend está activo:
   docker exec -it tryon_redis redis-cli INFO clients

   Ya NO debe haber una conexión BLPOP por cada contenedor Modal permitido.

7. Hacer primero una generación Modal normal y comprobar SIN cambios visibles:
   queued -> running -> completed
   outputs disponibles
   billing normal
   BackOffice muestra estado

8. Probar cancelación Modal.
9. Probar una generación con sobrecosto/result_locked si corresponde a tu set de pruebas.
10. Probar recovery:
    - iniciar generación Modal
    - esperar provider_job_id
    - apagar backend SIN cancelar Modal
    - volver a arrancar backend
    - confirmar que NO aparece un segundo FunctionCall
    - confirmar que obtiene el resultado del FunctionCall original

COMANDOS GIT DESPUÉS DE VALIDAR
===============================
git add .
git commit -m "fix: scale Modal orchestration without exhausting Redis"
git push

ROLLBACK
========
El MegaZIP es incremental. Para rollback, restaurar los 6 archivos modificados
desde el commit anterior. No agrega migraciones SQL ni cambia esquemas de BD.
