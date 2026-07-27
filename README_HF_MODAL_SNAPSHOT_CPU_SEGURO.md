# Hotfix Modal — snapshot CPU seguro

## Objetivo
Eliminar el crash loop causado por iniciar ComfyUI durante `@modal.enter(snap=True)`, fase en la que Modal no adjunta GPU.

## Qué queda dentro del snapshot
- Proceso Python principal de Modal y sus imports normales.
- Variables de entorno del runtime.
- Preparación de directorios, machine-id y enlaces seguros a volúmenes.
- Imports de `generation_runtime` y sus dependencias CPU (`httpx`, Pillow, etc.), cuando están disponibles.

## Qué no se intenta snapshottear
- ComfyUI.
- ComfyUI-Manager y custom nodes.
- CUDA.
- Flux/Klein, CLIP/Qwen, VAE, SAM3 u otros modelos.
- El subproceso de ComfyUI.

## Blindaje
Las preparaciones opcionales del snapshot están aisladas con `try/except`: si alguna falla, se registra y se omite, sin abortar la creación del snapshot.

Después del restore con GPU, ComfyUI arranca por `_start_process()` usando la ruta normal preexistente. No se exige que un proceso hijo sobreviva al snapshot.

## Archivos modificados
- `modal_app.py`
- `app/services/runtime_builder_service.py`

## Validaciones realizadas
- Compilación de ambos archivos Python.
- Generación real de `modal_app.py` desde la plantilla `_modal_app()`.
- Compilación del archivo exportado.
- `run_pipeline` permanece idéntico al ZIP base.
- `_start_process` permanece idéntico al ZIP base.
