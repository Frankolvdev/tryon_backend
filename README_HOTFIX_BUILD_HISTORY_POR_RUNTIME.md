# Hotfix: historial de Build & Deploy por runtime

## Alcance

Este parche corrige únicamente el listado de builds de la pestaña Build & Deploy.

El endpoint `GET /api/v1/admin/runtime-builder/builds` ahora filtra por el
`runtime_config_id` del perfil activo. Cada runtime muestra exclusivamente sus
propios builds y el campo `total` corresponde al mismo perfil.

## Archivo reemplazado

- `app/api/v1/endpoints/admin/runtime_builder.py`

## Sistemas no modificados

No se modifican la creación o ejecución de builds, deploy, exportadores,
proveedores, modelos, esquemas, migraciones, jobs ni otros endpoints.
