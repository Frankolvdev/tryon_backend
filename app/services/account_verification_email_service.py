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
        return str(getattr(settings, "FRONTEND_URL", "http://localhost:3001")).strip().rstrip("/")

    def _verification_url(self, *, email: str, purpose: str, token: str) -> str:
        route = "/reset-password" if purpose == "password_reset" else "/verify-account"
        return (
            f"{self._frontend_base_url()}{route}"
            f"?email={quote(email)}&purpose={quote(purpose)}&token={quote(token)}"
        )

    def _translate(self, db: Session, *, user_id: int, key: str, default: str, variables: dict | None = None) -> str:
        return i18n_service.translate(
            db, translation_key=key, user_id=user_id, variables=variables, default=default
        )

    @staticmethod
    def _layout(*, eyebrow: str, title: str, intro: str, content: str, warning: str) -> str:
        return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{escape(title)}</title></head>
<body style="margin:0;background:#070709;color:#f7f7f8;font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#070709;padding:34px 14px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:620px;background:#111116;border:1px solid #292931;border-radius:22px;overflow:hidden;">
<tr><td style="height:5px;background:linear-gradient(90deg,#4d0b14,#d52d42,#4d0b14);font-size:0">&nbsp;</td></tr>
<tr><td style="padding:34px 38px 16px;">
<table role="presentation" width="100%"><tr>
<td><div style="font-size:23px;font-weight:900;letter-spacing:.08em;">LUX<span style="color:#df3047">IA</span></div>
<div style="font-size:10px;color:#898994;letter-spacing:.18em;margin-top:4px;">AI FASHION STUDIO</div></td>
<td align="right"><span style="display:inline-block;border:1px solid #3a2026;background:#1a1114;color:#f07788;border-radius:999px;padding:8px 12px;font-size:10px;font-weight:700;letter-spacing:.12em;">CUENTA SEGURA</span></td>
</tr></table></td></tr>
<tr><td style="padding:18px 38px 8px;">
<div style="color:#e54a5f;font-size:11px;font-weight:800;letter-spacing:.14em;margin-bottom:12px;">{escape(eyebrow)}</div>
<h1 style="margin:0 0 14px;font-size:32px;line-height:1.12;color:#fff;">{escape(title)}</h1>
<p style="margin:0;color:#b7b7c0;font-size:15px;line-height:1.7;">{escape(intro)}</p>
</td></tr>
<tr><td style="padding:22px 38px 10px;">{content}</td></tr>
<tr><td style="padding:18px 38px 32px;">
<div style="border:1px solid #292931;background:#0b0b0e;border-radius:14px;padding:15px;color:#8f909a;font-size:12px;line-height:1.65;">🔒 {escape(warning)}</div>
</td></tr>
<tr><td style="border-top:1px solid #25252c;padding:22px 38px;color:#70717b;font-size:11px;line-height:1.6;">
Este mensaje fue enviado automáticamente por LUXIA. No respondas a este correo.<br>
© AI Fashion Studio · Seguridad y privacidad por diseño.
</td></tr>
</table></td></tr></table></body></html>"""

    def _build_content(
        self, db: Session, *, user_id: int, email: str, purpose: str,
        verification_method: str, otp: str | None, link_token: str | None,
        otp_expiration_minutes: int, email_link_expiration_minutes: int,
    ) -> tuple[str, str, str]:
        is_reset = purpose == "password_reset"
        subject = "Restablece tu contraseña de LUXIA" if is_reset else "Verifica tu cuenta de LUXIA"
        title = "Crea una nueva contraseña" if is_reset else "Confirma tu correo electrónico"
        intro = (
            "Recibimos una solicitud para recuperar el acceso a tu cuenta."
            if is_reset else
            "Estás a un paso de activar tu estudio creativo y proteger tu cuenta."
        )
        warning = (
            "Si no solicitaste este cambio, ignora el mensaje. Tu contraseña actual seguirá funcionando."
            if is_reset else
            "Si no creaste esta cuenta, puedes ignorar este mensaje con seguridad."
        )
        blocks = []
        text = [intro, ""]
        if otp:
            blocks.append(
                f'<div style="background:#0a0a0d;border:1px solid #302126;border-radius:16px;padding:22px;text-align:center;margin-bottom:16px;">'
                f'<div style="color:#8f9099;font-size:11px;letter-spacing:.12em;margin-bottom:10px;">CÓDIGO DE SEGURIDAD</div>'
                f'<div style="color:#fff;font-size:34px;font-weight:900;letter-spacing:8px;">{escape(otp)}</div>'
                f'<div style="color:#7d7e87;font-size:12px;margin-top:10px;">Caduca en {otp_expiration_minutes} minutos.</div></div>'
            )
            text += ["Código:", otp, f"Caduca en {otp_expiration_minutes} minutos.", ""]
        if link_token:
            url = self._verification_url(email=email, purpose=purpose, token=link_token)
            label = "Crear nueva contraseña" if is_reset else "Verificar mi correo"
            blocks.append(
                f'<div style="text-align:center;padding:8px 0 18px;">'
                f'<a href="{escape(url)}" style="display:inline-block;background:linear-gradient(135deg,#97182a,#d52d42);'
                f'color:#fff;text-decoration:none;font-weight:800;border-radius:13px;padding:16px 25px;">{escape(label)}</a>'
                f'<div style="color:#777883;font-size:12px;margin-top:14px;">El enlace caduca en {email_link_expiration_minutes} minutos.</div></div>'
                f'<div style="color:#777883;font-size:11px;line-height:1.6;word-break:break-all;">Si el botón no funciona, copia este enlace:<br>{escape(url)}</div>'
            )
            text += [label, url, f"Caduca en {email_link_expiration_minutes} minutos.", ""]
        text.append(warning)
        html = self._layout(
            eyebrow="RECUPERACIÓN DE ACCESO" if is_reset else "VERIFICACIÓN DE CUENTA",
            title=title, intro=intro, content="".join(blocks), warning=warning,
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
        self, db: Session, *, user_id: int, email: str, purpose: str,
        verification_method: str, otp: str | None, link_token: str | None,
        otp_expiration_minutes: int, email_link_expiration_minutes: int,
    ) -> None:
        from_email = str(getattr(settings, "SMTP_FROM_EMAIL", "")).strip()
        from_name = str(getattr(settings, "SMTP_FROM_NAME", "LUXIA AI Fashion Studio")).strip()
        if not from_email:
            raise RuntimeError("SMTP_FROM_EMAIL is not configured.")
        subject, text_body, html_body = self._build_content(
            db, user_id=user_id, email=email, purpose=purpose,
            verification_method=verification_method, otp=otp, link_token=link_token,
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
        logger.info("Account security email sent.", extra={
            "user_id": user_id, "purpose": purpose, "verification_method": verification_method,
        })


account_verification_email_service = AccountVerificationEmailService()
