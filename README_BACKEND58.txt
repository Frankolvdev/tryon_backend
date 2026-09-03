Backend58 - Modal Runtime Engine cache-buster in Dockerfile.modal

Base exacta:
- tryon_backend-main (56).zip

Producción modificada:
- app/services/runtime_context_generator_service.py

Qué corrige:
- _modal_dockerfile() ahora incluye COMFY_RUNTIME_ENGINE_CACHE_BUSTER.
- La instrucción que clona comfyui_runtime_engine imprime el cache-buster antes del git clone.
- Esto cambia Dockerfile.modal y evita reutilizar silenciosamente la capa anterior del Runtime Engine.

No modifica:
- pipeline/runtime.py
- workflows
- modelos/residency plan
- warmup workflow
- CUDA/VRAM
- GPU/region/concurrency
- billing
- SAM3 behavior
- RuntimeEngine06

Validación esperada:
- py_compile
- pytest del contrato Backend58

Después de aplicar:
1. Regenerar/exportar runtime.
2. Abrir Dockerfile.modal.
3. Confirmar COMFY_RUNTIME_ENGINE_CACHE_BUSTER=runtime-engine-06-diagnostics-20260902.
4. Build/Deploy.
5. En snapshot deben aparecer trazas [comfy-runtime-modal].
