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
        return str(
            getattr(settings, "FRONTEND_URL", "http://localhost:3001")
        ).strip().rstrip("/")

    def _verification_url(
        self,
        *,
        email: str,
        purpose: str,
        token: str,
    ) -> str:
        route = (
            "/reset-password"
            if purpose == "password_reset"
            else "/verify-account"
        )
        return (
            f"{self._frontend_base_url()}{route}"
            f"?email={quote(email)}"
            f"&purpose={quote(purpose)}"
            f"&token={quote(token)}"
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

    @staticmethod
    def _brand_icon() -> str:
        return """
        <table role="presentation" cellspacing="0" cellpadding="0">
          <tr>
            <td width="48" height="48" align="center" valign="middle"
                style="width:48px;height:48px;border:1px solid #4b1820;
                       border-radius:16px;background:#1b090c;color:#f87171">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none"
                   xmlns="http://www.w3.org/2000/svg"
                   stroke="#f87171" stroke-width="1.8"
                   stroke-linecap="round" stroke-linejoin="round">
                <path d="m12 3-1.2 4.1a4.6 4.6 0 0 1-3.1 3.1L3.6 11.4l4.1 1.2a4.6 4.6 0 0 1 3.1 3.1L12 19.8l1.2-4.1a4.6 4.6 0 0 1 3.1-3.1l4.1-1.2-4.1-1.2a4.6 4.6 0 0 1-3.1-3.1L12 3Z"/>
                <path d="m19 3-.45 1.55L17 5l1.55.45L19 7l.45-1.55L21 5l-1.55-.45L19 3Z"/>
              </svg>
            </td>
          </tr>
        </table>
        """

    @classmethod
    def _layout(
        cls,
        *,
        eyebrow: str,
        title: str,
        intro: str,
        content: str,
        warning: str,
    ) -> str:
        return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>{escape(title)}</title>
</head>
<body style="margin:0;padding:0;background:#030303;color:#f5f5f5;
             font-family:Arial,Helvetica,sans-serif">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
         style="width:100%;background:#030303">
    <tr>
      <td align="center" style="padding:36px 16px">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
               style="width:100%;max-width:620px;border:1px solid #1d1d20;
                      border-radius:28px;background:#0b0b0d;overflow:hidden;
                      box-shadow:0 20px 70px rgba(0,0,0,.45)">
          <tr>
            <td style="padding:30px 36px;border-bottom:1px solid #19191c;
                       background:#080809">
              <table role="presentation" cellspacing="0" cellpadding="0">
                <tr>
                  <td>{cls._brand_icon()}</td>
                  <td style="padding-left:16px">
                    <div style="margin:0;color:#fff;font-size:20px;
                                line-height:28px;font-weight:600;
                                letter-spacing:.22em">LUXIA</div>
                    <div style="margin-top:4px;color:#ef4444;font-size:10px;
                                line-height:15px;font-weight:600;
                                letter-spacing:.3em;text-transform:uppercase">
                      AI Fashion Studio
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <tr>
            <td style="padding:40px 36px 36px">
              <div style="margin:0;color:#ef4444;font-size:12px;
                          line-height:18px;font-weight:600;letter-spacing:.28em;
                          text-transform:uppercase">
                {escape(eyebrow)}
              </div>

              <h1 style="margin:12px 0 0;color:#fff;font-size:30px;
                         line-height:36px;font-weight:600;letter-spacing:-.025em">
                {escape(title)}
              </h1>

              <p style="margin:12px 0 0;color:#71717a;font-size:14px;
                        line-height:24px">
                {escape(intro)}
              </p>

              {content}

              <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
                     style="margin-top:28px">
                <tr>
                  <td style="padding:14px 16px;border:1px solid #26262a;
                             border-radius:12px;background:#101012;color:#71717a;
                             font-size:12px;line-height:20px">
                    {escape(warning)}
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <tr>
            <td style="padding:22px 36px;border-top:1px solid #19191c;
                       background:#080809;color:#3f3f46;font-size:11px;
                       line-height:18px;text-align:center">
              Tu seguridad y privacidad están protegidas por los controles de LUXIA.
              Este mensaje fue enviado automáticamente.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    @staticmethod
    def _otp_block(
        *,
        otp: str,
        expiration_minutes: int,
    ) -> str:
        return f"""
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
               style="margin-top:28px">
          <tr>
            <td align="center" style="padding:20px;border:1px solid #26262a;
                                     border-radius:12px;background:#050505">
              <div style="color:#52525b;font-size:10px;font-weight:600;
                          letter-spacing:.18em;text-transform:uppercase">
                Código de seguridad
              </div>
              <div style="margin-top:10px;color:#fff;font-size:30px;
                          font-weight:600;letter-spacing:.24em">
                {escape(otp)}
              </div>
              <div style="margin-top:10px;color:#52525b;font-size:11px">
                Caduca en {expiration_minutes} minutos
              </div>
            </td>
          </tr>
        </table>
        """

    @staticmethod
    def _link_block(
        *,
        url: str,
        label: str,
        expiration_minutes: int,
    ) -> str:
        safe_url = escape(url, quote=True)
        return f"""
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
               style="margin-top:28px">
          <tr>
            <td align="center">
              <a href="{safe_url}"
                 style="display:block;padding:15px 24px;border-radius:12px;
                        background:#c70a25;color:#fff;text-decoration:none;
                        font-size:14px;line-height:18px;font-weight:600;
                        box-shadow:0 12px 28px rgba(120,4,22,.3)">
                {escape(label)}
              </a>
            </td>
          </tr>
        </table>

        <p style="margin:18px 0 0;color:#52525b;font-size:11px;line-height:18px;
                  text-align:center">
          El enlace caduca en {expiration_minutes} minutos y solo puede usarse una vez.
        </p>

        <div style="margin-top:20px;padding:14px 16px;border:1px solid #1d1d20;
                    border-radius:12px;background:#050505">
          <div style="color:#52525b;font-size:10px;line-height:16px;
                      text-transform:uppercase;letter-spacing:.12em">
            Si el botón no funciona, copia este enlace
          </div>
          <div style="margin-top:8px;color:#a1a1aa;font-size:11px;
                      line-height:18px;word-break:break-all">
            {escape(url)}
          </div>
        </div>
        """

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
        is_reset = purpose == "password_reset"

        subject = (
            "Restablece tu contraseña de LUXIA"
            if is_reset
            else "Verifica tu cuenta de LUXIA"
        )
        title = (
            "Crea una nueva contraseña"
            if is_reset
            else "Confirma tu correo electrónico"
        )
        intro = (
            "Recibimos una solicitud para recuperar el acceso a tu cuenta."
            if is_reset
            else "Estás a un paso de activar tu estudio creativo y proteger tu cuenta."
        )
        warning = (
            "Si no solicitaste este cambio, ignora el mensaje. "
            "Tu contraseña actual seguirá funcionando."
            if is_reset
            else "Si no creaste esta cuenta, puedes ignorar este mensaje con seguridad."
        )

        blocks: list[str] = []
        text = [intro, ""]

        if otp:
            blocks.append(
                self._otp_block(
                    otp=otp,
                    expiration_minutes=otp_expiration_minutes,
                )
            )
            text.extend(
                [
                    "Código:",
                    otp,
                    f"Caduca en {otp_expiration_minutes} minutos.",
                    "",
                ]
            )

        if link_token:
            url = self._verification_url(
                email=email,
                purpose=purpose,
                token=link_token,
            )
            label = (
                "Crear nueva contraseña"
                if is_reset
                else "Verificar mi correo"
            )
            blocks.append(
                self._link_block(
                    url=url,
                    label=label,
                    expiration_minutes=email_link_expiration_minutes,
                )
            )
            text.extend(
                [
                    label,
                    url,
                    f"Caduca en {email_link_expiration_minutes} minutos.",
                    "",
                ]
            )

        text.append(warning)

        html = self._layout(
            eyebrow=(
                "RECUPERACIÓN DE ACCESO"
                if is_reset
                else "VERIFICACIÓN DE CUENTA"
            ),
            title=title,
            intro=intro,
            content="".join(blocks),
            warning=warning,
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
            return smtplib.SMTP_SSL(
                host,
                port,
                timeout=30,
                context=context,
            )
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
        from_email = str(
            getattr(settings, "SMTP_FROM_EMAIL", "")
        ).strip()
        from_name = str(
            getattr(settings, "SMTP_FROM_NAME", "LUXIA AI Fashion Studio")
        ).strip()

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

        username = str(
            getattr(settings, "SMTP_USERNAME", "")
        ).strip()
        password = str(
            getattr(settings, "SMTP_PASSWORD", "")
        )
        use_tls = bool(
            getattr(settings, "SMTP_USE_TLS", True)
        )
        use_ssl = bool(
            getattr(settings, "SMTP_USE_SSL", False)
        )
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
