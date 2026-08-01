# FIX 14B V3 — Import diferido del Runtime Engine en Modal

## Problema corregido

`modal deploy` importa `modal_app.py` primero en el equipo local. El archivo generado
importaba `comfyui_runtime_engine` en el nivel global, aunque el paquete solo se instala
dentro de `Dockerfile.modal`. Esto producía:

```text
ModuleNotFoundError: No module named 'comfyui_runtime_engine'
```

## Solución

El import de `ModalSnapshotAdapter` se mueve al bloque
`initialize_for_snapshot()` marcado con `@modal.enter(snap=True)`.

Así:

- el host local puede descubrir y desplegar la aplicación Modal sin instalar el Engine;
- la importación ocurre dentro de la imagen, donde el Engine ya está instalado;
- no se modifica Beam;
- no se modifica RunPod;
- se conserva el pipeline, proxy, cancelaciones y restore de Modal.

## Archivos incluidos

- `app/services/runtime_builder_service.py`
- `app/services/runtime_context_generator_service.py` (sin cambios funcionales; se incluye para mantener el par validado de 14B V3)
- `tests/test_megazip_14b_v3_contract.py`

## Aplicación

Descomprimir sobre la raíz del backend y reemplazar los archivos.

Después ejecutar:

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -m pytest tests/test_megazip_14b_v3_contract.py -v
python -m pytest tests -v
```

Reiniciar el backend y volver a exportar el runtime. No reutilizar el `modal_app.py`
exportado antes de este fix.
