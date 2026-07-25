# Backend — Profile & Separate MFA Foundation

Este ZIP prepara el backend para el próximo ZIP del BackOffice.

## Qué agrega

### Política MFA separada

En `account_security_settings`:

- `admin_mfa_required`
- `admin_mfa_totp_enabled`
- `admin_mfa_recovery_codes_enabled`
- `user_mfa_available`
- `user_mfa_required`
- `user_mfa_totp_enabled`
- `user_mfa_recovery_codes_enabled`

Esto permite configurar por separado:

1. administradores y trabajadores del BackOffice;
2. usuarios finales del futuro frontend.

### MFA de usuarios finales

Nuevos endpoints autenticados:

- `GET /api/v1/user-mfa/status`
- `POST /api/v1/user-mfa/setup`
- `POST /api/v1/user-mfa/confirm`
- `POST /api/v1/user-mfa/recovery-codes/regenerate`
- `POST /api/v1/user-mfa/disable`

Reutilizan la infraestructura TOTP cifrada que ya existía para administradores, sin duplicar secretos ni tablas.

### Login

El login ahora aplica la política correcta según el rol:

- administrador/trabajador: configuración `admin_mfa_*`;
- usuario final: configuración `user_mfa_*`.

El campo ya existente `mfa_setup_required` sigue indicando que una cuenta obligada todavía debe configurar MFA.

## Importante

Los métodos realmente implementados por el backend son:

- TOTP mediante aplicación autenticadora;
- códigos de recuperación.

No se inventaron SMS, WhatsApp ni biometría.

## Instalación

Descomprime directamente sobre:

`F:\PROYECTOS PERSONALES\TRYON\backend`

Luego ejecuta:

```powershell
.\.venv\Scripts\Activate.ps1
alembic upgrade head
python -m compileall app
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

## Verificación

Abre:

```text
http://127.0.0.1:8001/docs
```

Comprueba:

- `GET /api/v1/admin/account-security/settings`
- `PUT /api/v1/admin/account-security/settings`
- rutas `/api/v1/user-mfa/*`
- rutas existentes `/api/v1/admin-mfa/*`

## Nota sobre Alembic

La migración se enlaza al head público actual:

```text
22a5cd2a04fc
```

Si tu copia local tiene una migración posterior que todavía no está subida a GitHub, ejecuta:

```powershell
alembic heads
```

y cambia únicamente `down_revision` en:

```text
alembic/versions/9f2a6c7d8e10_add_separate_admin_user_mfa_policy.py
```

por el head local correspondiente antes de `alembic upgrade head`.

## Git

```powershell
git add .
git commit -m "Security - Separate admin and user MFA policy"
git push
```
