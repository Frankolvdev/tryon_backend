HOTFIX Backend55 - Modal Runtime Engine hardcoded ON

Base: tryon_backend-main (54).zip

Objetivo:
- Forzar Runtime Engine ON exclusivamente en la generación de runtimes Modal.
- Eliminar dependencia de TRYON_MODAL_RUNTIME_ENGINE_ENABLED para instalación/arranque del Engine.
- Mantener intacto el resto del Runtime Builder y el hotfix Backend54 (incluyendo SAM3 fuera del warmup legacy).

Archivos de producción modificados:
- app/services/runtime_builder_service.py

Cambios funcionales exactos:
1) RuntimeBuilderService.modal_runtime_engine_enabled(...) retorna True.
   Esto garantiza que el Dockerfile Modal generado incluya clone/install del Runtime Engine.
2) modal_app.py generado contiene RUNTIME_ENGINE_ENABLED = True.
   Esto evita que el runtime caiga silenciosamente al snapshot legacy por una variable de entorno perdida.

No se modifica:
- runtime_build_execution_service.py
- generation_runtime/runtime.py
- pipelines/workflows/loaders
- GPU/region/scaling/concurrency/timeouts
- billing/storage
- snapshot resident model selection
- SAM3 node/package/runtime guard

SAM3:
- Backend54 ya eliminó el warmup automático legacy de SAM3.
- Backend55 conserva esa eliminación sin cambios.

Validación realizada:
- python -m py_compile: OK
- comparación contra Backend54: 1 archivo de producción modificado
- pytest local bloqueado durante colección por dependencia ambiental ausente: psycopg2

IMPORTANTE:
Después de aplicar este hotfix hay que REGENERAR/BUILD y luego DEPLOY del runtime Modal.
Un deploy usando un contexto generado anteriormente puede conservar modal_app.py/Dockerfile viejos.

Log esperado durante snapshot:
- runtime_engine_enabled: true
- snapshot_mode: runtime_engine_gpu_snapshot
- no debe aparecer tryon-warmup-sam3
- deben observarse los residentes Flux2 + Mistral configurados en snapshot_resident_models
