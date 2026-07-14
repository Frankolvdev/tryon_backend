import logging
import smtplib
import ssl
from email.message import EmailMessage
from html import escape
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.i18n_service import (
    i18n_service,
)


logger = logging.getLogger(
    "app.email_change_email"
)


class EmailChangeEmailService:
    def _frontend_url(self) -> str:
        return str(
            getattr(
                settings,
                "FRONTEND_URL",
                "http://localhost:3000",
            )
        ).rstrip("/")

    def _smtp_connection(
        self,
    ) -> smtplib.SMTP:
        host = str(
            getattr(
                settings,
                "SMTP_HOST",
                "",
            )
        ).strip()

        port = int(
            getattr(
                settings,
                "SMTP_PORT",
                587,
            )
        )

        use_ssl = bool(
            getattr(
                settings,
                "SMTP_USE_SSL",
                False,
            )
        )

        if not host:
            raise RuntimeError(
                "SMTP_HOST is not configured."
            )

        context = ssl.create_default_context()

        if use_ssl:
            return smtplib.SMTP_SSL(
                host,
                port,
                timeout=30,
                context=context,
            )

        return smtplib.SMTP(
            host,
            port,
            timeout=30,
        )

    def _send(
        self,
        *,
        recipient: str,
        subject: str,
        text_body: str,
        html_body: str,
    ) -> None:
        from_email = str(
            getattr(
                settings,
                "SMTP_FROM_EMAIL",
                "",
            )
        ).strip()

        from_name = str(
            getattr(
                settings,
                "SMTP_FROM_NAME",
                "AI Virtual Try-On",
            )
        ).strip()

        if not from_email:
            raise RuntimeError(
                "SMTP_FROM_EMAIL is not configured."
            )

        message = EmailMessage()

        message["Subject"] = subject
        message["From"] = (
            f"{from_name} <{from_email}>"
        )
        message["To"] = recipient

        message.set_content(
            text_body
        )

        message.add_alternative(
            html_body,
            subtype="html",
        )

        username = str(
            getattr(
                settings,
                "SMTP_USERNAME",
                "",
            )
        ).strip()

        password = str(
            getattr(
                settings,
                "SMTP_PASSWORD",
                "",
            )
        )

        use_tls = bool(
            getattr(
                settings,
                "SMTP_USE_TLS",
                True,
            )
        )

        use_ssl = bool(
            getattr(
                settings,
                "SMTP_USE_SSL",
                False,
            )
        )

        server = self._smtp_connection()

        try:
            if use_tls and not use_ssl:
                server.starttls(
                    context=ssl.create_default_context()
                )

            if username:
                server.login(
                    username,
                    password,
                )

            server.send_message(
                message
            )

        finally:
            try:
                server.quit()
            except Exception:
                pass

    def send_new_email_verification(
        self,
        db: Session,
        *,
        user_id: int,
        old_email: str,
        new_email: str,
        otp: str | None,
        link_token: str | None,
        otp_expiration_minutes: int,
        link_expiration_minutes: int,
    ) -> None:
        subject = i18n_service.translate(
            db,
            user_id=user_id,
            translation_key=(
                "account.email_change."
                "verification.subject"
            ),
            default=(
                "Verify your new email address"
            ),
        )

        introduction = (
            "Confirm this email address to "
            "complete the change from "
            f"{old_email}."
        )

        text_parts = [
            introduction,
            "",
        ]

        html_parts = [
            "<!doctype html>",
            "<html><body "
            "style=\"font-family:Arial,sans-serif;\">",
            f"<p>{escape(introduction)}</p>",
        ]

        if otp:
            text_parts.extend(
                [
                    "Verification code:",
                    otp,
                    (
                        "This code expires in "
                        f"{otp_expiration_minutes} minutes."
                    ),
                    "",
                ]
            )

            html_parts.extend(
                [
                    "<p>Verification code:</p>",
                    (
                        "<p style=\"font-size:30px;"
                        "font-weight:bold;"
                        "letter-spacing:6px;\">"
                        f"{escape(otp)}"
                        "</p>"
                    ),
                    (
                        "<p>This code expires in "
                        f"{otp_expiration_minutes} "
                        "minutes.</p>"
                    ),
                ]
            )

        if link_token:
            url = (
                f"{self._frontend_url()}"
                "/confirm-email-change"
                f"?email={quote(new_email)}"
                f"&token={quote(link_token)}"
            )

            text_parts.extend(
                [
                    "Verify new email:",
                    url,
                    (
                        "This link expires in "
                        f"{link_expiration_minutes} minutes."
                    ),
                ]
            )

            html_parts.extend(
                [
                    (
                        "<p><a href=\""
                        f"{escape(url)}"
                        "\" style=\"display:inline-block;"
                        "padding:12px 20px;"
                        "background:#111;color:#fff;"
                        "text-decoration:none;"
                        "border-radius:6px;\">"
                        "Verify new email"
                        "</a></p>"
                    ),
                    (
                        "<p>This link expires in "
                        f"{link_expiration_minutes} "
                        "minutes.</p>"
                    ),
                ]
            )

        html_parts.extend(
            [
                "</body></html>",
            ]
        )

        self._send(
            recipient=new_email,
            subject=subject,
            text_body="\n".join(
                text_parts
            ),
            html_body="".join(
                html_parts
            ),
        )

    def send_old_email_notice(
        self,
        *,
        old_email: str,
        new_email: str,
    ) -> None:
        subject = (
            "Your account email was changed"
        )

        text_body = (
            "The email address associated with "
            "your account was changed to:\n\n"
            f"{new_email}\n\n"
            "If you did not make this change, "
            "contact support immediately."
        )

        html_body = (
            "<!doctype html>"
            "<html><body "
            "style=\"font-family:Arial,sans-serif;\">"
            "<p>The email address associated "
            "with your account was changed to:</p>"
            f"<p><strong>{escape(new_email)}</strong></p>"
            "<p>If you did not make this change, "
            "contact support immediately.</p>"
            "</body></html>"
        )

        self._send(
            recipient=old_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )


email_change_email_service = (
    EmailChangeEmailService()
)