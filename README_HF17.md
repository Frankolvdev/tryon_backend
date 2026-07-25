# MegaZIP 3A HF17 — Restore Runtime Launch + Bulk Actions

Corrige la regresión introducida por HF16.

Restaura:
- POST /api/v1/admin/runtime-builder/runtime-launch/preview
- GET /api/v1/admin/runtime-builder/runtime-launch/settings
- PUT /api/v1/admin/runtime-builder/runtime-launch/settings

Conserva:
- POST /api/v1/admin/runtime-builder/builds/bulk-delete
- POST /api/v1/admin/runtime-builder/builds/bulk-cancel

Este ZIP reemplaza únicamente:
- app/api/v1/endpoints/admin/runtime_builder.py

Requiere que HF16 ya haya agregado a app/schemas/runtime_builder.py:
- RuntimeBuildBulkRequest
- RuntimeBuildBulkResponse

No modifica schemas, modelos, servicios, migraciones ni configuración Docker.
