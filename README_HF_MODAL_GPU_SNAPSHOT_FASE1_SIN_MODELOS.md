# Hotfix Modal — GPU Snapshot fase 1 sin modelos

## Alcance estrictamente incremental

Este hotfix habilita GPU Memory Snapshot en Modal y captura:

- proceso de ComfyUI ya iniciado;
- imports y registro de custom nodes;
- servidor y puerto 8188 listos;
- inicialización de CUDA realizada por ComfyUI;
- estado general del runtime previo a cualquier generación.

No ejecuta ningún workflow durante `snap=True` y no precarga intencionalmente Flux, CLIP/Qwen, VAE, SAM3, LoRA ni otros pesos.

## Blindaje

No se modificaron:

- `run_pipeline()`;
- transporte y polling de Modal;
- cancelación Modal;
- reembolsos;
- estados de ejecución;
- concurrencia;
- contratos del payload;
- proxy ASGI;
- cierre normal del contenedor.

El restore valida que el proceso restaurado continúe vivo y que el puerto 8188 responda. Si la restauración experimental del proceso o socket falla, se registra `container_restore_fallback` y se usa automáticamente el arranque normal anterior para no dejar inutilizable la generación.

## Archivos modificados

- `modal_app.py`
- `app/services/runtime_builder_service.py`

La segunda modificación conserva la misma implementación dentro de la plantilla del builder para impedir que una futura regeneración de `modal_app.py` revierta el hotfix.

## Logs esperados

Durante creación del snapshot:

```text
snapshot_mode=gpu_runtime_without_models
comfyui_started=true
models_loaded=false
GPU Snapshot fase 1 listo
```

Durante una restauración exitosa:

```text
startup_mode=gpu_runtime_snapshot_without_models
comfyui_snapshotted=true
models_snapshotted=false
```

Fallback seguro:

```text
container_restore_fallback
startup_mode=normal_gpu_fallback_after_snapshot
```

## Aplicación

Descomprimir directamente sobre la raíz del backend y volver a desplegar Modal. El redeploy es obligatorio para invalidar el snapshot anterior y crear uno nuevo con GPU Snapshot habilitado.
