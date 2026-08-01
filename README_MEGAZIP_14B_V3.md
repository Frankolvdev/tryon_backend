# MegaZIP 14B V3 — Integración directa

Este ZIP fue generado sobre el backend completo proporcionado el 1 de agosto de
2026. No usa instaladores ni búsquedas de anclas.

## Reemplaza solamente

- `app/services/runtime_builder_service.py`
- `app/services/runtime_context_generator_service.py`

## Añade

- `tests/test_megazip_14b_v3_contract.py`

## Blindaje

Se conservan `run_pipeline`, cancelaciones, proxies, Beam y RunPod. La
integración del engine está limitada al build y lifecycle Modal.

## Aplicación

Descomprime directamente sobre la raíz del backend y acepta reemplazar archivos.

```powershell
python -m compileall app
pytest tests/test_megazip_14b_v3_contract.py
```

Después:

```powershell
git add .
git commit -m "feat: integrate optional Modal snapshot runtime engine"
git push
```

No ejecutes nuevamente los instaladores 14B anteriores.
