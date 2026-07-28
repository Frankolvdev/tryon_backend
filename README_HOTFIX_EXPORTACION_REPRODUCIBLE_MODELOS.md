# Hotfix encapsulado: exportación reproducible de modelos

Este parche modifica únicamente `app/services/runtime_model_volume_export_service.py`.

La localización de modelos vuelve a consumir `config.models` del perfil seleccionado, como en el commit funcional. No vuelve a ejecutar el resolvedor de workflows durante la exportación.

Se conserva:
- soporte de modelos externos mediante `extra_model_paths.yaml`;
- deduplicación por archivo físico;
- destinos Local, Docker Volume, Modal, RunPod Serverless y Beam;
- lógica de copia específica de cada proveedor;
- exportador de runtime y validador de workflows sin cambios.
