# Hotfix resolver central Modal / RunPod / Beam

Este hotfix mueve al resolvedor central la deduplicación por archivo físico que Modal ya aplicaba durante la exportación.

- Cada runtime sigue analizando su propio workflow actual.
- Modal, RunPod y Beam llaman al mismo `resolve_runtime_models(config)`.
- El algoritmo de detección de referencias no cambia.
- `required_models` contiene una sola entrada por `target_path` físico resuelto.
- Las referencias repetidas se conservan en `workflow_references`.

Archivo modificado:

- `app/services/runtime_import_service.py`
