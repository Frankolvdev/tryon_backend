# FIX — Protección de activación de proveedores de almacenamiento

## Corrige

- Un proveedor ya no puede seleccionarse para archivos nuevos si no supera una prueba real de conexión.
- Local valida creación, escritura y eliminación de un archivo de prueba.
- Amazon S3 y Cloudflare R2 validan credenciales, configuración, bucket y acceso mediante `head_bucket`.
- El proveedor activo solo cambia después de una prueba exitosa.
- La prueba local devuelve un mensaje visible para evitar alertas vacías.
- Las pruebas remotas también devuelven un mensaje legible.

## Aplicación

Descomprimir sobre la raíz del Backend.

```powershell
cd "F:\PROYECTOS PERSONALES\TRYON\backend"
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
python -m compileall -q app tests
python -m pytest tests/test_storage_provider_activation_guard_contract.py -v
```

No requiere migración Alembic. Reiniciar completamente el Backend.
