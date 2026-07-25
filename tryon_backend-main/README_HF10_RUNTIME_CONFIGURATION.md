# HF10 — Runtime Configuration como fuente única

Descomprime este ZIP directamente en la raíz de `tryon_backend` y ejecuta:

```powershell
python apply_hf10_runtime_configuration.py
python -m compileall app
uvicorn app.main:app --reload --port 8001
```

Resultado:

- `build_name` sincroniza internamente `name` y `runtime_name`.
- `image_name` sincroniza internamente `registry_image`.
- `container_name` se conserva en `runtime_launch`.
- La exportación y compilación existentes usan los nombres de Runtime Configuration.
- No requiere migración destructiva de base de datos.
