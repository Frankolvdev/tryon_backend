
Backend59 - Modal terminal reconciliation + RuntimeEngine07 cache invalidation

Base exacta:
- tryon_backend-main (57).zip

Producción modificada:
- app/services/modal_pipeline_adapter_service.py
- app/services/runtime_builder_service.py

Qué corrige:
1. La supervisión async de Modal sigue usando get.aio() como ruta normal.
2. En paralelo, revisa el call graph durable como safety-net.
3. INIT_FAILURE / FAILURE / TIMEOUT / TERMINATED se convierten inmediatamente en error terminal,
   en vez de dejar la ejecución 'running' hasta el timeout general.
4. Si Modal reporta SUCCESS, el resultado aún debe llegar. SUCCESS sin payload después
   de una gracia corta se considera error.
5. El finalizador existente conserva la validación de imágenes requeridas antes de marcar completed.
6. Se cambia el cache-buster del Runtime Engine a runtime-engine-07-python310-tomli-20260903
   para obligar a Modal a instalar el Engine07 y no reutilizar la capa anterior.

No modifica:
- pipeline/runtime.py
- workflows
- residency plan
- modelos
- billing
- GPU/region/concurrency
- cancelación remota
- almacenamiento final de imágenes

Pruebas:
- test_modal_async_wait_runtime.py
- test_modal_terminal_reconciliation_contract.py
- test_modal_cancel_recovery_no_retry_contract.py
- test_backend59_modal_terminal_reconciliation_and_engine07_contract.py
