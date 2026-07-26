# Hotfix Modal — Snapshot con precarga fija de modelos

## Alcance

Precarga encapsulada antes de la captura del snapshot de Modal para el workflow fijo actual.

Modelos incluidos en esta primera fase segura:

- `flux2-vae.safetensors`
- `qwen_3_8b.safetensors`
- `Flux2-Klein-9B-True-v2-bf16.safetensors`
- `sam3.pt`

Los LoRA y `realDream_klein9BV1.safetensors` no se precargan en esta fase para evitar presión excesiva de VRAM y mantener intacta la transición gestionada por los nodos `PurgeVRAM` del workflow real.

## Blindaje

- La precarga ocurre únicamente dentro de `initialize_for_snapshot()`.
- `run_pipeline()` no fue modificado.
- La cancelación, polling, reembolsos, proxy ASGI, concurrencia y contratos no fueron modificados.
- Si el warmup falla, expira o un nodo no existe, se registra el fallo y se continúa con el snapshot normal.
- El workflow real no se modifica ni se ejecuta durante el warmup.
- Los nodos `PurgeVRAM` permanecen intactos.

## Funcionamiento

1. Se instala un nodo interno aislado en el arranque del contenedor.
2. ComfyUI inicia normalmente.
3. Se consultan las definiciones reales de los loaders mediante `/object_info`.
4. Se envía un prompt interno mínimo con los IDs y loaders conocidos.
5. El nodo interno mantiene referencias fuertes y solicita promoción a GPU de forma best-effort.
6. Cuando el warmup termina, Modal captura el snapshot.
7. Si cualquier paso falla, se captura el snapshot normal sin bloquear el despliegue.

## Variables de entorno

```env
TRYON_MODAL_SNAPSHOT_MODEL_WARMUP=true
TRYON_MODAL_SNAPSHOT_MODEL_WARMUP_TIMEOUT=420
```

Para desactivarlo sin modificar código:

```env
TRYON_MODAL_SNAPSHOT_MODEL_WARMUP=false
```

## Logs

Buscar:

```text
"event": "snapshot_model_warmup"
```

Éxito esperado:

```json
{
  "event": "snapshot_model_warmup",
  "completed": true
}
```

Fallback seguro:

```json
{
  "event": "snapshot_model_warmup",
  "completed": false,
  "fallback": "normal_snapshot"
}
```

## Primera ejecución

La carga pesada se realiza durante la construcción del snapshot al desplegar el runtime. Una vez creado correctamente, la primera petición real también debe restaurarse desde ese snapshot. No es necesario ejecutar previamente una generación de usuario para activarlo.
