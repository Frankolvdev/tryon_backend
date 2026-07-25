MEGAZIP 4P - BACKEND

Corrige:
- GET /api/v1/admin/runtime-builder/deployment-providers
- POST /api/v1/admin/runtime-builder/builds/{build_id}/deployments

Los endpoints usan RuntimeBuildExecutionService existente.
No se inventan proveedores ni respuestas simuladas.

Validación:
python -m compileall app
