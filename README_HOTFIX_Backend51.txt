Backend51 — Modal Runtime Engine + Flux2 snapshot + ComfyUI 0.31

Cambios:
- Default de modelos residentes nuevos: Flux2 Dev + mistral Flux2 TE.
- runtime-engine.toml generado acepta ComfyUI 0.15 y 0.31 con strict_version=true.
- No cambia pipeline, purge, DynamicVRAM ni ejecución.

IMPORTANTE:
- Para perfiles existentes, snapshot_resident_models ya persistido NO se sobreescribe.
  En Backoffice seleccionar explícitamente:
  diffusion_models/flux2_dev_fp8mixed (1).safetensors
  text_encoders/mistral_3_small_flux2_fp8.safetensors
- TRYON_MODAL_RUNTIME_ENGINE_ENABLED debe quedar true ANTES de generar/reconstruir el runtime Modal.
- Requiere aplicar también RuntimeEngine04 al repo comfyui_runtime_engine que el Dockerfile clona desde GitHub.
