# HF63 — Modal ComfyUI + GPU Warm Snapshot (blindado)

## Alcance

Este hotfix modifica exclusivamente el runtime de Modal para que el snapshot CPU+GPU se capture después de:

1. preparar rutas y enlaces de modelos;
2. iniciar ComfyUI;
3. esperar a que el puerto 8188 esté listo;
4. ejecutar un warmup aislado de VAE, CLIP, UNET y SAM3;
5. mantener referencias fuertes a los objetos cargados antes de la captura.

Tras restaurar, Modal verifica que el proceso de ComfyUI sobrevivió y que el puerto está disponible. No reinicia ComfyUI.

## Archivos

- `modal_app.py`
- `app/services/runtime_builder_service.py`

## Blindaje

No se modifican Beam, RunPod, cancelaciones, pipeline, resultados, proxy, volúmenes, GPU seleccionada, concurrencia ni tiempos de inactividad.

## Aplicación

1. Reemplazar los archivos.
2. Reiniciar FastAPI.
3. Exportar nuevamente el runtime Modal.
4. Hacer Deploy de Modal.
5. No requiere Build Docker manual adicional.

## Logs esperados

- `snapshot_mode=comfyui_gpu_warm_snapshot`
- `comfyui_started=true`
- `models_loaded=true`
- `restored_from_snapshot=true`
- `comfyui_snapshotted=true`
- `models_snapshotted=true`
