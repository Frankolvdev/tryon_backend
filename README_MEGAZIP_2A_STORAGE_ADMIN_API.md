# MegaZIP 2A — Backend API de configuración de almacenamiento

Complemento incremental para el Storage Engine multi-proveedor.

## Incluye
- Respuesta administrativa completa para Local, Amazon S3 y Cloudflare R2.
- Guardado independiente de credenciales y configuración de S3/R2.
- Cambio del proveedor activo para archivos nuevos.
- Edición del directorio local.
- Auditoría de cambios.
- Compatibilidad total con los endpoints existentes de archivos.

## Aplicación
```powershell
python -m compileall -q app tests
python -m pytest tests/test_storage_provider_admin_contract.py -v
```
No requiere migración Alembic adicional.
