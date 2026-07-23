# MEGA21 — Runtime requirements fix + exportación sin ZIP

## Cambios

- Elimina la dependencia externa `packaging` que impedía iniciar el backend.
- Corrige el renderizado de dependencias detectadas por el flujo actual:
  - `qrcode` + `[pil]` → `qrcode[pil]`
  - `onnxruntime-gpu` + `; marker` → requisito con marcador válido
  - versiones normales conservan `==`.
- La exportación utiliza el mismo análisis de workflow, modelos, Custom Nodes y dependencias.
- Deja de ejecutar `shutil.make_archive(...)` al finalizar la exportación.
- El directorio exportado queda como contexto directo para Docker/Modal, sin duplicarlo en un ZIP gigantesco.
- `archive_path` se devuelve vacío para conservar el contrato actual de la API.
- `last_export_archive` se limpia en la configuración persistida.
- Cuando Modal está seleccionado, exporta `modal_app.py` y, al no copiar modelos, `extra_model_paths.yaml`.

## Validación

```powershell
python -m compileall app
pytest tests/test_runtime_builder_requirements.py -q
```
