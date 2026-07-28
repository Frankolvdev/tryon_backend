# Hotfix resolver único Modal / RunPod / Beam

- Única función pública: `RuntimeImportService.resolve_workflow_models`.
- Analiza exclusivamente `inputs` ejecutables.
- Nunca usa `widgets_values` del editor.
- Deduplica por archivo físico resuelto.
- Modal, RunPod y Beam consumen la misma lista persistida en `config.models`.
