# FIX Cloudflare R2: activación conserva credenciales

Corrige el caso donde **Probar conexión** funciona, pero **Usar para archivos nuevos** borra las credenciales guardadas al reenviar campos secretos vacíos o nulos.

## Aplicación

Copie el contenido sobre la raíz del Backend y ejecute:

```powershell
.\.venv\Scripts\Activate.ps1
python -m compileall -q app tests
python -m pytest tests/test_storage_activation_preserves_credentials_contract.py tests/test_storage_provider_activation_guard_contract.py -v
```

No requiere migración Alembic. Reinicie el Backend.
