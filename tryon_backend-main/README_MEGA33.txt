MEGA33 — Alias locales de Custom Nodes + ComfyLiterals obligatorio

Cambios incrementales sobre MEGA32:
- Conserva toda la generación, Dockerfile, CUDA 12.8, Python 3.11, Torch cu128,
  constraints, dependencias nativas y validaciones existentes.
- El exportador continúa copiando exclusivamente desde la instalación local de
  ComfyUI; no descarga, actualiza ni sustituye Custom Nodes desde GitHub.
- Reconoce ComfyUI-Execute-Python cuando la carpeta local se llama execute-python.
- Reconoce WAS Node Suite cuando la carpeta local se llama was-ns.
- Mantiene ComfyLiterals como Custom Node obligatorio. Si no existe localmente,
  conserva la advertencia real y no lo descarga automáticamente.
- La detección ignora mayúsculas, espacios, guiones y guiones bajos.
- Mantiene la detección de duplicados y la normalización de requirements.

Archivos modificados:
- app/services/runtime_builder_service.py
- app/services/runtime_context_generator_service.py

Después de aplicar el ZIP, reinicia el backend y genera una exportación nueva.
