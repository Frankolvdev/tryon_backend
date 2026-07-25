MEGAZIP 4M - HOTFIX DEFINITIVO RUTAS LORA RGTHREE

Este ZIP modifica únicamente:

- app/services/comfyui_prompt_preprocessor_service.py
- app/services/comfyui_local_adapter_service.py
- tests/test_comfyui_prompt_preprocessor_service.py

Aplicación desde la raíz del backend:

python APLICAR_MEGAZIP_4M.py
python -m compileall app
pytest tests/test_comfyui_prompt_preprocessor_service.py -q

Después reinicia el backend.

Resultado esperado de pytest:

3 passed
