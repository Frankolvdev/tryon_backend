# Hotfix Modal: snapshot CPU de modelos, estrictamente incremental

Este parche parte del backend entregado el 26-07-2026 y modifica únicamente el mecanismo de preparación del snapshot.

## Se conserva sin cambios

- restore_after_snapshot
- run_pipeline
- ejecución y entrega de resultados
- cancelación
- polling
- reintentos
- timeouts de ejecución
- limpieza de procesos
- fallback existente
- endpoints ASGI existentes
- control de concurrencia

## Cambio aplicado

- GPU snapshot desactivado para evitar el error de restauración CUDA 222.
- Snapshot normal CPU conservado.
- VAE, Qwen/CLIP, Flux2 Klein y SAM3 se cargan de forma secuencial en CPU antes del snapshot.
- No se ejecuta load_models_gpu ni .to("cuda") durante snap=True.
- Cada modelo tiene log y fallo aislado.
- La misma modificación se replica en la plantilla de runtime_builder_service.py.

## Logs

- snapshot_cpu_warmup_model
- snapshot_cpu_warmup
- container_snapshot_initialize

## Variables

TRYON_MODAL_SNAPSHOT_MODEL_WARMUP=true
TRYON_MODAL_SNAPSHOT_MODEL_WARMUP_TIMEOUT=420
TRYON_MODAL_CPU_MEMORY_MB=65536
TRYON_MODAL_MIN_CONTAINERS=0

## Validación

Se comprobó por AST/hash que restore_after_snapshot, run_pipeline y _start_process permanecen idénticos a la base recibida. Los únicos métodos modificados en modal_app.py son los relacionados con el snapshot CPU y initialize_for_snapshot.
