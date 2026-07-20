# Backend 01G SYNC — OAuth completo y sincronizado

Este paquete sustituye de forma coherente los archivos OAuth entregados en los
incrementos 01G anteriores. No cambia el login tradicional, MFA, recuperación
de contraseña ni la verificación por correo.

## Correcciones incluidas

- Compatibilidad con Python 3.10 (`str, Enum`; no usa `StrEnum`).
- Schemas y endpoints sincronizados, incluyendo `OAuthGrantExchangeRequest`.
- Flujo de inicio, callback y canje temporal de OAuth.
- Cliente Google OpenID Connect.
- Registro y consulta de identidades en `oauth_accounts`.
- Estado público de proveedores sin exponer credenciales.
- Migración Alembic de `oauth_accounts` incluida de forma idempotente a nivel de entrega.

## Verificación

```powershell
python -m compileall app alembic
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Con Redis iniciado, comprueba:

```text
GET http://127.0.0.1:8001/api/v1/oauth/providers
```

## Configuración local

```env
FRONTEND_URL=http://localhost:3003
```

En Google Cloud, configura como URI autorizada:

```text
http://127.0.0.1:8001/api/v1/oauth/google/callback
```
