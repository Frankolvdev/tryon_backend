MEGAZIP FINAL BACKEND

Archivos incluidos:
- app/services/comfyui_prompt_preprocessor_service.py
- app/services/comfyui_local_adapter_service.py
- app/api/v1/endpoints/admin/runtime_builder.py
- tests/test_comfyui_prompt_preprocessor_service.py

Corrige:
1. Claves de LoRA de rgthree con separadores de Windows.
2. Segunda barrera inmediatamente antes de POST /prompt.
3. Docker Run basado en RuntimeLaunchSettings:
   imagen configurada, nombre, GPU, puertos, reinicio, volúmenes y argumentos.
4. Evita la combinación inválida --rm + --restart.

Validación:
python -m compileall app
python -m pytest tests/test_comfyui_prompt_preprocessor_service.py -q
