# Hotfix Runtime Builder: rutas LoRA de rgthree

Este hotfix agrega al contexto de compilación el script `scripts/apply_runtime_hotfixes.py` y lo ejecuta durante `docker build` después de copiar los Custom Nodes.

El script corrige de forma idempotente `rgthree-comfy/py/power_prompt_utils.py` para convertir separadores de Windows (`\\`) a separadores Linux (`/`) dentro de `get_lora_by_filename`.

Mensajes esperados durante la compilación:

- `[HOTFIX] Normalización de rutas de LoRA de rgthree aplicada.`
- `[HOTFIX] La normalización de rutas de rgthree ya estaba aplicada.`
- `[HOTFIX] rgthree-comfy no está instalado; parche omitido.`

Después de instalar el hotfix, vuelve a exportar el contexto y recompilar la imagen. Las exportaciones creadas antes del hotfix no se modifican automáticamente.
