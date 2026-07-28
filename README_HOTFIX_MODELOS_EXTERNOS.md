# Hotfix export runtime: modelos externos

Corrige únicamente el cálculo de la ruta lógica de modelos durante Export Runtime.

- Conserva el flujo multiproveedor restaurado.
- No modifica el resolvedor de workflows.
- Admite archivos físicos fuera de `ComfyUI/models` mediante `extra_model_paths.yaml`.
- Usa `target_path` persistido como ruta lógica dentro del runtime.
