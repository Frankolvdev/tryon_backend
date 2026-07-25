# MEGA20 — Runtime requirements fix + Modal export

Cambio incremental del Backend. Conserva el análisis existente de workflow, custom nodes, dependencias y modelos.

## Corrige

- `qrcode==[pil]` se exporta como `qrcode[pil]`.
- `onnxruntime-gpu==; marcador` se exporta como `onnxruntime-gpu; marcador`.
- Todas las dependencias se validan como PEP 508 antes de generar/build.
- El build se cancela antes de transferir el contexto si una dependencia es inválida.

## Modal

Cuando `target_platform` o las notas indican Modal:

- genera `modal_app.py`;
- puede montar un Modal Volume;
- si todos los modelos usan estrategia `volume`, `external-volume`, `external_volume` o `mounted`, genera `extra_model_paths.yaml`;
- no cambia el análisis ni la selección de modelos del workflow;
- deja GPU Memory Snapshot como opción experimental para la prueba real.

## Verificación

```powershell
python -m compileall app
pytest tests/test_runtime_builder_requirements.py -q
```
