# FIX Backend: selección autenticada de archivos de biblioteca

Sirve los bytes del archivo desde el proveedor original mediante `storage_service.read_bytes()`.
Compatible con Local, Cloudflare R2, Amazon S3 y el proveedor histórico S3.
No cambia guardado, cuotas, URLs de miniatura ni proveedor activo.
No requiere migración Alembic.
