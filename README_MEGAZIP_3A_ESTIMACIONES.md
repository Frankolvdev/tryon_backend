# MegaZIP 3A — Backend de estimaciones históricas

- Usa la duración inicial solo cuando no existe ninguna ejecución completada válida del módulo.
- Aprende desde la primera generación completada.
- Usa hasta las últimas 50 ejecuciones completadas del mismo módulo.
- Prioriza `real_provider_seconds` / `real_provider_duration_ms` y usa fallbacks durables.
- Pondera más las ejecuciones recientes.
- Filtra valores extremos cuando hay suficientes muestras.
- Expone cantidad de muestras, confianza y fecha de actualización.
- No usa cancelaciones ni fallos para estimar una ejecución normal.

Validación:

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -m compileall -q app tests
python -m pytest tests/test_historical_generation_estimate_learning.py tests/test_generation_estimate_snapshot_contract.py -v
```

No requiere migración Alembic.
