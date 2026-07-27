# Hotfix Modal — GPU exacta y snapshot básico

## Alcance

Este parche es estrictamente incremental y modifica únicamente:

- `modal_app.py`
- `app/services/runtime_builder_service.py`

## GPU de Modal

- `A100-80GB` se conserva exactamente y se envía a Modal con el identificador oficial.
- Se valida la GPU antes de construir la clase de Modal.
- Se normaliza el valor histórico `A10G` a `A10`, que es el identificador oficial actual.
- Un valor desconocido falla temprano con un mensaje claro.

## Snapshot

Se elimina el código muerto del warmup CPU de modelos:

- no se crea el nodo `TryonSnapshotWarmupSink`;
- no se intentan cargar VAE, CLIP/Qwen, Flux o SAM3 en RAM durante el snapshot;
- no se usan las variables `TRYON_MODAL_SNAPSHOT_MODEL_WARMUP*`.

Se conserva únicamente el snapshot básico seguro de Modal:

- `enable_memory_snapshot=True`;
- `experimental_options={"enable_gpu_snapshot": False}`;
- preparación de directorios e imports seguros;
- ComfyUI y CUDA arrancan normalmente después del restore.

## Blindaje conservado

No se modificó la lógica de:

- `run_pipeline`;
- entrega de resultados;
- polling;
- cancelación;
- reintentos;
- timeouts;
- concurrencia;
- endpoints ASGI;
- guard selectivo de `PurgeVRAM` y SAM3.

## Validaciones realizadas

- Compilación Python de ambos archivos.
- Generación real de `modal_app.py` desde la plantilla `_modal_app()`.
- Parseo AST correcto del archivo generado.
- `run_pipeline` conserva exactamente el mismo AST.
- El único cambio dentro de `_start_process` fue retirar la instalación del nodo CPU obsoleto.
