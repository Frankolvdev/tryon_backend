# MegaZIP 3A HF16 — Runtime Build Bulk Delete

Corrige el error:

POST /api/v1/admin/runtime-builder/builds/bulk-delete -> 405 Method Not Allowed

## Cambios

- Restaura `POST /runtime-builder/builds/bulk-delete`.
- Restaura `POST /runtime-builder/builds/bulk-cancel`.
- Agrega los contratos `RuntimeBuildBulkRequest` y `RuntimeBuildBulkResponse`.
- Omite builds activos o actualmente en ejecución.
- No elimina imágenes Docker; elimina únicamente los registros de compilación permitidos.
- No modifica Runtime Configuration, exportaciones, volúmenes ni Dockerfile.

## Archivos

- `app/api/v1/endpoints/admin/runtime_builder.py`
- `app/schemas/runtime_builder.py`
