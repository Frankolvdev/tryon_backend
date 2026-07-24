# MEGA35 — Runtime models, SAM3 y diagnóstico adaptable

Este parche incremental corrige el Runtime Builder sin cambiar la arquitectura existente.

## Cambios

- El volumen externo universal se monta en `/models` para Docker, Modal y RunPod.
- `extra_model_paths.yaml` usa `base_path: /models`.
- `clip` apunta a `text_encoders` y se registra `sam3: sam3`.
- La exportación de modelos continúa siendo selectiva, excepto `models/sam3`, que se copia completa y recursivamente.
- El manifiesto del volumen declara `/models` como ruta de montaje.
- Al arrancar, si existe `/models/sam3`, se crea automáticamente:
  `/app/ComfyUI/models/sam3 -> /models/sam3`.
- Se genera un diagnóstico de GPU/PyTorch/CUDA/FlashAttention/xFormers/Triton.
- `COMFYUI_EXTRA_ARGS` permite agregar flags compatibles con el proveedor sin reconstruir la imagen.
- El fallback de ComfyUI permanece intacto: no se fuerza una optimización que el hardware o PyTorch no soporten.

## Verificación

```powershell
python -m compileall app
pytest tests/test_runtime_builder_requirements.py tests/test_runtime_builder_portable_models.py
```

Después, vuelve a exportar el runtime y el volumen de modelos para que los archivos generados incorporen los cambios.
