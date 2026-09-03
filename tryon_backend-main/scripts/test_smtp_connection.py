"""Comprueba la conexión SMTP configurada en el backend sin enviar credenciales al código."""

import smtplib
from app.core.config import settings


def main() -> None:
    if not settings.SMTP_HOST:
        raise RuntimeError("SMTP_HOST no está configurado.")
    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        raise RuntimeError("SMTP_USERNAME y SMTP_PASSWORD no están configurados.")

    smtp_class = smtplib.SMTP_SSL if settings.SMTP_USE_SSL else smtplib.SMTP
    with smtp_class(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as client:
        client.ehlo()
        if settings.SMTP_USE_TLS and not settings.SMTP_USE_SSL:
            client.starttls()
            client.ehlo()
        client.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)

    print("Conexión SMTP correcta.")


if __name__ == "__main__":
    main()
