# Backend 01G-A — OAuth Foundation

Primera entrega incremental del módulo OAuth multi-provider.

## Incluye

- Modelo `OAuthAccount` para vincular una cuenta local con Google, GitHub,
  Facebook o Apple.
- Contrato común `OAuthProvider`.
- Registro explícito de proveedores.
- Esquemas normalizados para perfiles y autorizaciones OAuth.
- Soporte estructural para PKCE.

## Compatibilidad

Esta entrega no registra rutas, no cambia el login por correo y contraseña,
no modifica JWT, refresh tokens, MFA, recuperación de contraseña ni registro.

Todavía no activa ningún proveedor. La integración del modelo en
`app/models/__init__.py`, la migración Alembic y el proveedor Google se
realizarán en la siguiente entrega, una vez aplicada esta base.

## Verificación rápida

```powershell
python -m compileall app
```
