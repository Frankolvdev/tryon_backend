MEGAZIP 4L - REPARACIÓN SEGURA DE LORAS RGTHREE

Corrige:

1. external_ai_job_service.py con una versión válida del propio repositorio Git.
2. Las rutas de LoRA almacenadas como CLAVES por rgthree Power Lora Loader.
3. Una segunda normalización justo antes del POST /prompt a ComfyUI.
4. Una validación final que impide enviar rutas de modelos con separadores de Windows.

Aplicación desde la raíz del backend:

python APLICAR_MEGAZIP_4L.py
python -m compileall app
pytest tests/test_comfyui_prompt_preprocessor_service.py -q

Después reinicia el backend.
