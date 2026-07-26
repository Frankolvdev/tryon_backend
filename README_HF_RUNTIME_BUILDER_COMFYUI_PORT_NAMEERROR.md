# Hotfix Runtime Builder: COMFYUI_PORT NameError

Corrige exclusivamente la plantilla de exportación de `modal_app.py`.

## Problema

La plantilla se genera mediante un `rf-string`, pero una referencia interna quedó sin escapar:

```python
url = f"http://127.0.0.1:{COMFYUI_PORT}{path}"
```

Durante la exportación, Python intentaba resolver `COMFYUI_PORT` en el proceso del backend y producía:

```text
name 'COMFYUI_PORT' is not defined
```

## Corrección

La plantilla ahora conserva las llaves para el archivo exportado:

```python
url = f"http://127.0.0.1:{{COMFYUI_PORT}}{{path}}"
```

## Alcance

No modifica:

- ejecución de pipelines;
- cancelación;
- polling;
- reintentos;
- fallbacks;
- cleanup;
- cierre de workers;
- `modal_app.py` principal;
- snapshot CPU aplicado anteriormente.

## Validaciones realizadas

- compilación de `runtime_builder_service.py`;
- ejecución real de `_modal_app(...)`;
- verificación de `COMFYUI_PORT = 8188` en el archivo generado;
- compilación del `modal_app.py` generado.
