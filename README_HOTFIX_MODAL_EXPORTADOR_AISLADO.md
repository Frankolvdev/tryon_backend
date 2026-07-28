# Hotfix: exportador Modal aislado

Este parche modifica únicamente el camino de selección/validación de modelos durante la exportación de Modal.

- Modal usa `config.models`, la lista ya analizada y persistida.
- Modal no vuelve a ejecutar `RuntimeImportService.resolve_runtime_models()` durante la exportación.
- RunPod y Beam conservan el resolvedor actual y sus configuraciones independientes.
- No se modifican endpoints, jobs, validador de workflow, file managers ni plantillas de proveedores.

Archivos:
- `app/services/runtime_builder_service.py`
- `app/services/runtime_context_generator_service.py`
