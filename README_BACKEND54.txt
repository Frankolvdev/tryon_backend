HOTFIX Backend54 - Modal Runtime Engine env propagation + remove legacy SAM3 warmup

Base revisada:
  tryon_backend-main (53).zip

Archivos de producción modificados:
  app/services/runtime_build_execution_service.py
  app/services/runtime_builder_service.py

Test agregado:
  tests/test_modal_runtime_profile_env_and_no_sam3_warmup_contract.py

Cambios:
1) Ambas rutas de modal deploy incorporan las variables TRYON_MODAL_* guardadas
   en el perfil Runtime Builder. Esto permite que
   TRYON_MODAL_RUNTIME_ENGINE_ENABLED=true llegue al proceso que importa modal_app.py.
2) Los valores críticos del proveedor/Motor IA (GPU, región, scaling, timeout)
   se aplican DESPUÉS del perfil y conservan autoridad.
3) El warmup legacy del snapshot queda desactivado por defecto.
4) SNAPSHOT_MODEL_WARMUP_TARGETS queda vacío; se elimina tryon-warmup-sam3.
5) Si alguien habilita explícitamente el warmup legacy sin targets, retorna de
   forma segura con reason=no_legacy_warmup_targets.

NO se modificó:
  runpod_worker/generation_runtime/runtime.py
  pipeline/workflows
  Runtime Engine repo
  loaders/modelos
  billing/tokens
  configuración GPU/región/concurrencia
  snapshot resident model selection Flux2/TE

Validación:
  python -m py_compile: OK en los 2 archivos de producción + test.
  test contractual nuevo: 2 passed.
  Tests heredados que importan toda la app no pudieron recolectarse en este
  contenedor porque falta psycopg2. Con SECRET_KEY definido, el único bloqueo
  restante fue ModuleNotFoundError: psycopg2; no fue una regresión del parche.

Resultado esperado próximo deploy:
  runtime_engine_enabled: true
  no tryon-warmup-sam3
  no TBGSAM3ModelLoaderAdvanced como snapshot warmup
  Runtime Engine prepara los residentes Flux2 + text encoder configurados.
