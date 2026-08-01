# MegaZIP 14B — Backend Modal Runtime Engine Integration

Descomprimir sobre la raíz de `tryon_backend`.

## Modifica únicamente

- `app/services/runtime_builder_service.py`
- `app/services/runtime_context_generator_service.py`

## Blindaje

No modifica Beam, RunPod, `run_pipeline`, cancelaciones, `function_call_id`,
proxy HTTP/WebSocket, escalado ni concurrencia.

## Flag

```env
TRYON_MODAL_RUNTIME_ENGINE_ENABLED=true
```

Con `false`, se conserva el lifecycle Modal anterior.

## Engine durante build

```dockerfile
ARG COMFY_RUNTIME_ENGINE_GIT_URL=https://github.com/Frankolvdev/comfyui_runtime_engine.git
ARG COMFY_RUNTIME_ENGINE_GIT_REF=main
```

Antes de producción, cambia `DEFAULT_RUNTIME_ENGINE_REF` por el hash exacto del
commit validado del MegaZIP 14A.

## Archivos generados

- `runtime-engine.toml`
- `modal-snapshot-warmup.json`
- `modal_app.py`
- `Dockerfile.modal`

El warmup carga solo `realDream_klein9BV1.safetensors`.

## Aplicar

```powershell
python .\APLICAR_MEGAZIP_14B.py
python -m compileall app
pytest tests/test_megazip_14b_modal_engine_contract.py
```

Luego exporta nuevamente el runtime Modal y realiza build/deploy solo de Modal.

## Git

```powershell
git add .
git commit -m "feat: integrate optional Modal snapshot runtime engine"
git push
```
