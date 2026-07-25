# Backend 01D — política de verificación de correo

Este ZIP no crea endpoints nuevos. Configura en la base de datos los campos que
el backend ya utiliza para:

- exigir verificación;
- usar enlace por correo;
- bloquear el login antes de verificar;
- aplicar un cooldown mínimo de 60 segundos;
- limitar reenvíos por hora;
- mantener vigencia del enlace.

## Uso

Desde la raíz de `tryon_backend`:

```powershell
python scripts/configure_appweb_email_verification.py
```

Después reinicia FastAPI.

## Importante

Las cuentas creadas antes de activar esta política pueden conservar su estado
anterior. Para probar el flujo completo usa una dirección nueva o corrige el
estado de la cuenta de prueba desde el BackOffice.
