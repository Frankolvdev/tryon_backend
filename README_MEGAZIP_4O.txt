MEGAZIP 4O BACKEND

Revisión del repositorio actualizado:
- El preprocesador todavía no normalizaba claves de inputs.loras.
- queue_prompt todavía enviaba workflow directamente.

Este ZIP aplica directamente:
- normalización de claves rgthree;
- normalización de valores de rutas;
- validación final antes de POST /prompt;
- pruebas del caso Power Lora Loader.

Validación:
python -m compileall app
python -m pytest tests/test_comfyui_prompt_preprocessor_service.py -q
