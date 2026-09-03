# Mailjet SMTP para verificación de registro

El backend ya contiene:

- configuración SMTP en `app/core/config.py`;
- router `/api/v1/account-verification`;
- servicio `account_verification_email_service.py`;
- campo `users.is_verified`.

Este ZIP no duplica esos módulos. Añade una plantilla segura de variables y una prueba de conexión.

## Configuración

1. Regenera las credenciales de Mailjet que fueron compartidas públicamente.
2. Valida en Mailjet el correo o dominio que usarás como remitente.
3. Copia las variables de `.env.mailjet.example` al `.env` real.
4. Sustituye únicamente los valores `REEMPLAZAR_...`.
5. Reinicia FastAPI.

## Prueba SMTP

Desde la raíz del backend, con el entorno virtual activo:

```powershell
python -m scripts.test_smtp_connection
```

Debe imprimir:

```text
Conexión SMTP correcta.
```

El registro del App Web ahora envía `accept_terms: true` y redirige a `/verify-email`.
No inicia sesión automáticamente antes de verificar la cuenta.
