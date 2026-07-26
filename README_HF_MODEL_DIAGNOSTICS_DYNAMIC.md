# Hotfix — Diagnóstico dinámico de modelos Modal/ComfyUI

Este ZIP es incremental y solo añade observabilidad. No modifica cancelación, reembolsos, polling, contratos, proxy, concurrencia ni el flujo de ejecución.

## Archivos modificados

- `modal_app.py`
- `app/services/runtime_builder_service.py`

## Activación

El diagnóstico está activo por defecto. Puede desactivarse con:

```env
TRYON_MODAL_MODEL_DIAGNOSTICS=false
```

## Logs nuevos

Busque eventos `[tryon-modal-trace]` con:

- `event=model_diagnostics`
- `phase=before_pipeline`
- `phase=after_pipeline`

El inventario se obtiene dinámicamente de cualquier workflow incluido en el payload. Solo inspecciona; no modifica el JSON enviado a ComfyUI.
