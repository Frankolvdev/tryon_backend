# Backend 09C — Restaurar MFA administrativo

Este ZIP corrige el cambio que alteró el login administrativo.

## Comportamiento restaurado

- MFA de inicio de sesión se aplica únicamente a administradores.
- Si `admin_mfa_required=false`, el administrador entra con correo y contraseña.
- Si `admin_mfa_required=true` y ya tiene MFA configurado:
  1. valida correo y contraseña;
  2. responde `MFA_REQUIRED`;
  3. el mismo formulario muestra el campo de código;
  4. valida TOTP o código de recuperación;
  5. entra al dashboard.
- Si MFA es obligatorio y la cuenta administrativa todavía no está enrolada, devuelve `mfa_setup_required=true` y abre `/mfa/setup`.
- Los usuarios finales no usan el MFA administrativo.

## Usuarios finales

Para el futuro frontend se conserva la seguridad de verificación de cuenta que ya existía:

- OTP;
- enlace por email;
- ambos;
- deshabilitado.

Eso se configura con:

- `verification_required`
- `verification_method`

No se obliga a usar la tabla de credenciales MFA administrativas.

## Archivo reemplazado

`app/services/auth_service.py`

## Instalación

Descomprime sobre el backend y ejecuta:

```powershell
.\.venv\Scripts\Activate.ps1
python -m compileall app
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

No requiere migración nueva.

## Prueba

1. Activa MFA administrativo.
2. Inicia sesión con correo y contraseña.
3. Debe aparecer el campo para el código.
4. Introduce el código de tu aplicación.
5. Debe abrir `/dashboard`.

## Git

```powershell
git add .
git commit -m "Security - Restore administrative MFA login flow"
git push
```
