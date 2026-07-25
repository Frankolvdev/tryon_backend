MegaZIP 4Q5 - Modal ComfyUI Port Fix

Corrección:
- Alinea el puerto público de modal.web_server con el puerto real de ComfyUI.
- ComfyUI y el health check usan ahora el puerto 8188 tanto en Modal como en Docker/local.

Archivo modificado:
- app/services/runtime_builder_service.py

Aplicación:
- Descomprimir el ZIP directamente sobre la raíz del backend y reemplazar el archivo existente.
- Regenerar el runtime y volver a desplegarlo desde el BackOffice.
