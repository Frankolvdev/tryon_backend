from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from html import escape
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.i18n_service import i18n_service

logger = logging.getLogger("app.account_verification_email")


class AccountVerificationEmailService:
    def _frontend_base_url(self) -> str:
        return str(getattr(settings, "FRONTEND_URL", "http://localhost:3003")).strip().rstrip("/")

    def _action_url(self, *, email: str, purpose: str, token: str) -> str:
        route = "/reset-password" if purpose == "password_reset" else "/verify-account"
        return (
            f"{self._frontend_base_url()}{route}"
            f"?email={quote(email)}&purpose={quote(purpose)}&token={quote(token)}"
        )

    def _translate(
        self,
        db: Session,
        *,
        user_id: int,
        key: str,
        default: str,
        variables: dict | None = None,
    ) -> str:
        return i18n_service.translate(
            db,
            translation_key=key,
            user_id=user_id,
            variables=variables,
            default=default,
        )

    def _html(
        self,
        *,
        eyebrow: str,
        title: str,
        intro: str,
        button_label: str | None,
        button_url: str | None,
        otp: str | None,
        expiration: str,
        ignore: str,
    ) -> str:
        button = ""
        if button_label and button_url:
            button = f"""
            <table role="presentation" width="100%" style="margin:30px 0 22px">
              <tr><td align="center">
                <a href="{escape(button_url, quote=True)}"
                   style="display:inline-block;padding:16px 28px;border-radius:14px;
                          background:linear-gradient(135deg,#761120,#e1324d);
                          color:#fff;text-decoration:none;font-weight:800">
                  {escape(button_label)}
                </a>
              </td></tr>
            </table>
            """

        otp_block = ""
        if otp:
            otp_block = f"""
            <div style="margin:26px 0;padding:22px;border:1px solid #2a2a31;
                        border-radius:16px;background:#111116;text-align:center">
              <div style="margin-bottom:9px;color:#8c8d98;font-size:11px;
                          font-weight:800;letter-spacing:.16em;text-transform:uppercase">
                Código de seguridad
              </div>
              <div style="color:#fff;font-size:30px;font-weight:900;letter-spacing:.22em">
                {escape(otp)}
              </div>
            </div>
            """

        return f"""<!doctype html>
<html lang="es">
<body style="margin:0;background:#050507;color:#f6f6f8;font-family:Arial,Helvetica,sans-serif">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"
       style="background:#050507">
<tr><td align="center" style="padding:36px 16px">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"
       style="max-width:620px;border:1px solid #25252c;border-radius:26px;
              overflow:hidden;background:#0a0a0e;box-shadow:0 30px 90px rgba(0,0,0,.55)">
<tr><td style="padding:28px 34px;border-bottom:1px solid #202027;
               background:linear-gradient(135deg,#171218,#0a0a0e)">
<table role="presentation"><tr>
<td style="width:44px;height:44px;border-radius:14px;text-align:center;
           background:linear-gradient(145deg,#e23952,#71111f);
           color:#fff;font-size:20px;font-weight:900">L</td>
<td style="padding-left:12px">
<div style="color:#fff;font-size:20px;font-weight:900">LUXIA</div>
<div style="margin-top:3px;color:#777985;font-size:9px;font-weight:800;
            letter-spacing:.19em;text-transform:uppercase">AI Fashion Studio</div>
</td></tr></table>
</td></tr>
<tr><td style="padding:42px 38px 34px">
<div style="margin-bottom:14px;color:#ef455d;font-size:10px;font-weight:900;
            letter-spacing:.22em;text-transform:uppercase">{escape(eyebrow)}</div>
<h1 style="margin:0;color:#fff;font-size:34px;line-height:1.12">{escape(title)}</h1>
<p style="margin:18px 0 0;color:#a0a1ab;font-size:15px;line-height:1.75">
{escape(intro)}
</p>
{otp_block}
{button}
<div style="margin-top:24px;padding:15px 16px;border:1px solid #25252d;
            border-radius:14px;background:#101014;color:#8c8d98;
            font-size:12px;line-height:1.65">{escape(expiration)}</div>
<p style="margin:22px 0 0;color:#666873;font-size:12px;line-height:1.65">
{escape(ignore)}
</p>
</td></tr>
<tr><td style="padding:22px 38px;border-top:1px solid #202027;
               background:#08080b;color:#565862;font-size:11px;line-height:1.6">
Mensaje automático de LUXIA. Nunca compartas enlaces ni códigos de seguridad.
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""

    def _build_content(
        self,
        db: Session,
        *,
        user_id: int,
        email: str,
        purpose: str,
        verification_method: str,
        otp: str | None,
        link_token: str | None,
        otp_expiration_minutes: int,
        email_link_expiration_minutes: int,
    ) -> tuple[str, str, str]:
        password_reset = purpose == "password_reset"

        if password_reset:
            subject = "Restablece tu contraseña de LUXIA"
            eyebrow = "RECUPERACIÓN SEGURA"
            title = "Crea una nueva contraseña"
            intro = (
                "Recibimos una solicitud para recuperar el acceso a tu cuenta. "
                "Utiliza el enlace seguro para establecer una nueva contraseña."
            )
            button_label = "Restablecer contraseña"
        else:
            subject = self._translate(
                db,
                user_id=user_id,
                key="account.verification.email.subject",
                default="Verifica tu cuenta de LUXIA",
            )
            eyebrow = "ACTIVA TU CUENTA"
            title = "Verifica tu correo electrónico"
            intro = self._translate(
                db,
                user_id=user_id,
                key="account.verification.email.greeting",
                default="Confirma que esta dirección te pertenece para activar y proteger tu cuenta.",
            )
            button_label = self._translate(
                db,
                user_id=user_id,
                key="account.verification.email.link_label",
                default="Verificar correo",
            )

        ignore = self._translate(
            db,
            user_id=user_id,
            key="account.verification.email.ignore",
            default="Si no solicitaste esta acción, ignora el mensaje. Tu cuenta permanecerá protegida.",
        )

        url = (
            self._action_url(email=email, purpose=purpose, token=link_token)
            if link_token
            else None
        )
        minutes = email_link_expiration_minutes if link_token else otp_expiration_minutes
        expiration = f"Este acceso vence en {minutes} minutos y solo puede utilizarse una vez."

        text = [title, "", intro, ""]
        if otp:
            text += ["Código de seguridad:", otp, ""]
        if url:
            text += [button_label, url, ""]
        text += [expiration, "", ignore]

        html = self._html(
            eyebrow=eyebrow,
            title=title,
            intro=intro,
            button_label=button_label if url else None,
            button_url=url,
            otp=otp,
            expiration=expiration,
            ignore=ignore,
        )
        return subject, "\n".join(text), html

    def _smtp_connection(self) -> smtplib.SMTP:
        host = str(getattr(settings, "SMTP_HOST", "")).strip()
        port = int(getattr(settings, "SMTP_PORT", 587))
        use_ssl = bool(getattr(settings, "SMTP_USE_SSL", False))
        if not host:
            raise RuntimeError("SMTP_HOST is not configured.")
        context = ssl.create_default_context()
        if use_ssl:
            return smtplib.SMTP_SSL(host, port, timeout=30, context=context)
        return smtplib.SMTP(host, port, timeout=30)

    def send_verification(
        self,
        db: Session,
        *,
        user_id: int,
        email: str,
        purpose: str,
        verification_method: str,
        otp: str | None,
        link_token: str | None,
        otp_expiration_minutes: int,
        email_link_expiration_minutes: int,
    ) -> None:
        from_email = str(getattr(settings, "SMTP_FROM_EMAIL", "")).strip()
        from_name = str(getattr(settings, "SMTP_FROM_NAME", "LUXIA")).strip()
        if not from_email:
            raise RuntimeError("SMTP_FROM_EMAIL is not configured.")

        subject, text_body, html_body = self._build_content(
            db,
            user_id=user_id,
            email=email,
            purpose=purpose,
            verification_method=verification_method,
            otp=otp,
            link_token=link_token,
            otp_expiration_minutes=otp_expiration_minutes,
            email_link_expiration_minutes=email_link_expiration_minutes,
        )

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = f"{from_name} <{from_email}>"
        message["To"] = email
        message.set_content(text_body)
        message.add_alternative(html_body, subtype="html")

        username = str(getattr(settings, "SMTP_USERNAME", "")).strip()
        password = str(getattr(settings, "SMTP_PASSWORD", ""))
        use_tls = bool(getattr(settings, "SMTP_USE_TLS", True))
        use_ssl = bool(getattr(settings, "SMTP_USE_SSL", False))
        context = ssl.create_default_context()

        server = self._smtp_connection()
        try:
            if use_tls and not use_ssl:
                server.starttls(context=context)
            if username:
                server.login(username, password)
            server.send_message(message)
        finally:
            try:
                server.quit()
            except Exception:
                pass

        logger.info(
            "Account security email sent.",
            extra={
                "user_id": user_id,
                "purpose": purpose,
                "verification_method": verification_method,
            },
        )


account_verification_email_service = AccountVerificationEmailService()
