# Backend 09B — Registrar Account Security Router

## Error corregido

El endpoint existía en:

`app/api/v1/endpoints/admin/account_security.py`

pero ese módulo no estaba importado ni registrado en:

`app/api/v1/endpoints/admin/router.py`

Por eso FastAPI respondía:

```text
GET /api/v1/admin/account-security/settings
404 Not Found
```

## Cambio

Se registra:

```python
admin_router.include_router(
    account_security.router,
    tags=["Admin - Account Security"],
)
```

Ahora quedan disponibles:

```text
GET /api/v1/admin/account-security/settings
PUT /api/v1/admin/account-security/settings
GET /api/v1/admin/account-security/challenges
POST /api/v1/admin/account-security/users/{user_id}/verify
POST /api/v1/admin/account-security/users/{user_id}/resend
POST /api/v1/admin/account-security/users/{user_id}/cancel
GET /api/v1/admin/account-security/unverified-accounts
POST /api/v1/admin/account-security/unverified-accounts/cleanup
```

## Instalación

Descomprime directamente sobre:

`F:\PROYECTOS PERSONALES\TRYON\backend`

No requiere una migración nueva.

Ejecuta:

```powershell
.\.venv\Scripts\Activate.ps1
python -m compileall app
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

## Verificación

Abre:

```text
http://127.0.0.1:8001/docs
```

La ruta debe aparecer. También puedes probarla sin token:

```powershell
curl -i http://127.0.0.1:8001/api/v1/admin/account-security/settings
```

Una respuesta `401` o `403` significa que la ruta ya existe y exige autenticación. Ya no debe devolver `404`.

## Git

```powershell
git add .
git commit -m "Security - Register account security admin router"
git push
```
