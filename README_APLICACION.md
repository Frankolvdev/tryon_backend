# FIX Backend — Módulos borrador + eliminación segura + previews de almacenamiento

BASE
tryon_backend-main - 2026-08-07T195856.127.zip

MÓDULOS DE GENERACIÓN

1. Crear módulo como borrador
- Endpoint ya era nullable en Backend y se conserva así.
- El motor ahora también puede ser NULL.
- Un módulo nuevo puede crearse solo con su ficha básica.
- Si no tiene motor, queda INACTIVO obligatoriamente.
- El motor y endpoint se configuran después desde Editar.
- La ejecución falla cerrada si por cualquier vía se intenta ejecutar un módulo sin motor.
- No se utiliza "simulated" como motor ficticio para representar "todavía no elegido".

2. Eliminar módulo
El endpoint DELETE ya existía. Se blinda su comportamiento:
- Si el módulo NUNCA tuvo ejecuciones: puede borrarse físicamente.
- Si tiene al menos una ejecución: NO se elimina.
  Debe dejarse inactivo para conservar historial.

Esto es necesario porque generation_module_executions tiene FK ON DELETE CASCADE;
permitir el hard-delete destruiría historial operativo y podría comprometer
trazabilidad financiera.

3. Export/clone
Se adapta únicamente para tolerar módulos borrador con engine=NULL.
No cambia el formato ni las operaciones existentes de módulos configurados.

ALMACENAMIENTO

Al servir un StorageFile:
- se conserva content_type guardado si es específico;
- si viene vacío/application/octet-stream/binary/octet-stream, el backend
  intenta inferir el MIME por original_filename/object_key;
- no se modifica el archivo ni el registro guardado;
- esto permite mostrar correctamente resultados .png/.jpg/.webp/etc que
  proveedores/runtimes registraron con MIME genérico.

NO MODIFICA
- bytes almacenados
- proveedor original del archivo
- S3/R2/local routing
- generación runtime configurada
- fórmulas financieras
- pricing
- FIFO
- snapshots
- tokens/promociones
- Caja
- Stripe
- Modal/RunPod/Beam

MIGRACIÓN OBLIGATORIA
alembic upgrade head

HEAD ESPERADO
05g_module_draft_engine (head)

VALIDACIÓN
- python -m compileall: OK
- alembic heads: 05g_module_draft_engine (head)
- 22 contratos módulos/readiness/storage: PASSED
- 105 contratos acumulados financieros/promocionales/storage/módulos: PASSED

COMANDOS
alembic upgrade head
alembic heads
python -m compileall -q app tests alembic/versions

python -m pytest -q `
  tests/test_generation_module_draft_storage_contract.py `
  tests/test_generation_configuration_readiness_contract.py `
  tests/test_generation_configuration_readiness_relation_contract.py `
  tests/test_storage_provider_admin_contract.py `
  tests/test_multi_provider_storage_contract.py

GIT
git add .
git commit -m "fix: support safe module drafts deletes and storage image previews"
git push
