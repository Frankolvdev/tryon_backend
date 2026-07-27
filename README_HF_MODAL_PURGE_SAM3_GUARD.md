# Hotfix Modal — PurgeVRAM adaptativo y caché SAM3 blindada

## Alcance

Este ZIP modifica exclusivamente el generador del runtime. No cambia endpoints, contratos, polling, colas, cancelaciones, reembolsos ni la ejecución del pipeline.

## Comportamiento

El contexto generado incorpora automáticamente `/app/ComfyUI/custom_nodes/zzz_tryon_runtime_guard`.

El guard:

- intercepta `LayerUtility: PurgeVRAM V2` sin cambiar el workflow JSON;
- registra VRAM antes y después de cada purga;
- conserva modelos solamente cuando la memoria libre supera el umbral seguro;
- ejecuta el `PurgeVRAM V2` original cuando hay presión de memoria;
- libera la caché SAM3 antes del purgado completo si la memoria es insuficiente;
- reutiliza SAM3 entre loaders equivalentes mientras sea seguro;
- ante cualquier excepción, vuelve inmediatamente al método original.

## Variables

- `TRYON_SELECTIVE_PURGE=true`
- `TRYON_SELECTIVE_PURGE_MIN_FREE_GB=28`
- `TRYON_PROTECT_SAM3=true`
- `TRYON_FALLBACK_ORIGINAL_PURGE=true`

Para restaurar el comportamiento exacto anterior sin recompilar código, usar:

```env
TRYON_SELECTIVE_PURGE=false
TRYON_PROTECT_SAM3=false
TRYON_FALLBACK_ORIGINAL_PURGE=true
```

## Logs

Los eventos se imprimen con el prefijo:

```text
[tryon-runtime-guard]
```

Eventos principales: `guard_ready`, `purge_selective_keep_models`, `purge_full_low_memory`, `purge_original`, `sam3_cache_store`, `sam3_cache_hit`, `sam3_cache_released_for_pressure` y `purge_guard_error`.
