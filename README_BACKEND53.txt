HOTFIX Backend53 - Modal async client blindado

Archivos tocados:
- app/services/modal_pipeline_adapter_service.py
- tests/test_modal_async_wait_runtime.py

Objetivo:
- Evitar Modal AsyncUsageWarning durante await_result_async.
- Mantener submit/spawn, poll legacy y cancelacion en sus rutas sincronas existentes.
- Crear/restaurar el cliente por una ruta async solo durante supervision asyncio.
- FunctionCall.from_id permanece sin .aio porque en Modal actual es un constructor lazy sin I/O.

Validacion realizada:
- py_compile OK
- 23 tests relevantes OK:
  * test_modal_async_wait_runtime.py
  * test_modal_async_orchestration_scaling_contract.py
  * test_modal_cancel_recovery_no_retry_contract.py
  * test_generation_configuration_readiness_contract.py

No toca:
- runtime_builder_service.py
- pipelines/workflows
- billing
- DB/migraciones
- purge VRAM
- Runtime Engine
- snapshot settings
