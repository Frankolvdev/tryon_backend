# MEGA26 — Native wheels build dependencies

Correcciones incrementales sobre MEGA25:

- Añade GCC/G++ y herramientas de compilación mediante `build-essential`.
- Añade `python3-dev` y `pkg-config` para extensiones nativas como `pycocotools`.
- Añade las cabeceras FFmpeg requeridas para compilar `av` cuando no existe wheel compatible.
- Aplica el cambio a ambos generadores de Dockerfile del Runtime Builder.
- Conserva la ruta Modal `/app/ComfyUI/models` y todos los arreglos anteriores.
