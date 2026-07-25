MEGAZIP 4J — NORMALIZACIÓN DE RUTAS ANTES DE COMFYUI

Este correctivo:
- elimina del generador el parche que modificaba rgthree-comfy;
- elimina apply_runtime_hotfixes.py del contexto y del Dockerfile;
- agrega un preprocesador de prompts;
- normaliza rutas Windows justo antes de enviar el workflow;
- conserva intactos los textos libres;
- funciona para Docker Local, RunPod y proveedores futuros porque se integra
  en el punto común de preparación del workflow.

APLICACIÓN

1. Descomprime el ZIP directamente en la raíz del backend.
2. Ejecuta:

   python APLICAR_MEGAZIP_4J.py

3. Valida:

   python -m compileall app
   python -m pytest tests/test_comfyui_prompt_preprocessor_service.py -q

4. Reinicia el backend.
5. En Runtime Builder vuelve a usar "Validar y generar archivos".
6. Compila de nuevo. Ya no debe existir el paso:
   RUN python /tmp/apply_runtime_hotfixes.py

El aplicador conserva copias .mega4j.bak de los dos archivos modificados.
