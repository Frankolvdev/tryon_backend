# MEGAZIP 2 — Runtime Builder Build & Deploy

Añade historial persistente, construcción Docker en segundo plano, logs consultables, smoke test, publicación al registro y activación de la imagen sobre las configuraciones RunPod activas.

## Requisitos del host constructor
- Docker Engine y Buildx
- Acceso al registro (`docker login`)
- Permisos de escritura en `RUNTIME_BUILDS_DIR`

Ejecutar `alembic upgrade head` antes de iniciar el backend.
