import logging
import smtplib
import ssl
from email.message import EmailMessage
from html import escape
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.i18n_service import i18n_service


logger = logging.getLogger(
    "app.account_verification_email"
)


class AccountVerificationEmailService:
    def _frontend_base_url(self) -> str:
        base_url = str(
            getattr(
                settings,
                "FRONTEND_URL",
                "http://localhost:3000",
            )
        ).strip()

        return base_url.rstrip("/")

    def _verification_url(
        self,
        *,
        email: str,
        purpose: str,
        token: str,
    ) -> str:
        return (
            f"{self._frontend_base_url()}"
            "/verify-account"
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
        subject = self._translate(
            db,
            user_id=user_id,
            key="account.verification.email.subject",
            default="Verify your account",
        )

        greeting = self._translate(
            db,
            user_id=user_id,
            key="account.verification.email.greeting",
            default="Verify your email address to activate your account.",
        )

        ignore_message = self._translate(
            db,
            user_id=user_id,
            key="account.verification.email.ignore",
            default=(
                "If you did not request this verification, "
                "you can ignore this message."
            ),
        )

        text_parts = [
            greeting,
            "",
        ]

        html_parts = [
            "<!doctype html>",
            "<html>",
            "<body style=\"font-family:Arial,sans-serif;"
            "line-height:1.5;color:#222;\">",
            f"<p>{escape(greeting)}</p>",
        ]

        if otp:
            otp_label = self._translate(
                db,
                user_id=user_id,
                key="account.verification.email.otp_label",
                default="Your verification code is:",
            )

            otp_expiration = self._translate(
                db,
                user_id=user_id,
                key="account.verification.email.otp_expiration",
                default=(
                    "This code expires in {minutes} minutes."
                ),
                variables={
                    "minutes": otp_expiration_minutes,
                },
            )

            text_parts.extend(
                [
                    otp_label,
                    otp,
                    otp_expiration,
                    "",
                ]
            )

            html_parts.extend(
                [
                    f"<p>{escape(otp_label)}</p>",
                    (
                        "<p style=\"font-size:30px;"
                        "font-weight:bold;"
                        "letter-spacing:6px;\">"
                        f"{escape(otp)}"
                        "</p>"
                    ),
                    f"<p>{escape(otp_expiration)}</p>",
                ]
            )

        if link_token:
            verification_url = self._verification_url(
                email=email,
                purpose=purpose,
                token=link_token,
            )

            link_label = self._translate(
                db,
                user_id=user_id,
                key="account.verification.email.link_label",
                default="Verify email",
            )

            link_expiration = self._translate(
                db,
                user_id=user_id,
                key="account.verification.email.link_expiration",
                default=(
                    "This link expires in {minutes} minutes."
                ),
                variables={
                    "minutes": email_link_expiration_minutes,
                },
            )

            text_parts.extend(
                [
                    link_label,
                    verification_url,
                    link_expiration,
                    "",
                ]
            )

            html_parts.extend(
                [
                    (
                        "<p>"
                        "<a href=\""
                        f"{escape(verification_url)}"
                        "\" style=\"display:inline-block;"
                        "padding:12px 20px;"
                        "background:#111;"
                        "color:#fff;"
                        "text-decoration:none;"
                        "border-radius:6px;\">"
                        f"{escape(link_label)}"
                        "</a>"
                        "</p>"
                    ),
                    f"<p>{escape(link_expiration)}</p>",
                ]
            )

        text_parts.append(
            ignore_message
        )

        html_parts.extend(
            [
                f"<p>{escape(ignore_message)}</p>",
                "</body>",
                "</html>",
            ]
        )

        return (
            subject,
            "\n".join(text_parts),
            "".join(html_parts),
        )

    def _smtp_connection(self) -> smtplib.SMTP:
        smtp_host = str(
            getattr(
                settings,
                "SMTP_HOST",
                "",
            )
        ).strip()

        smtp_port = int(
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

        if not smtp_host:
            raise RuntimeError(
                "SMTP_HOST is not configured."
            )

        context = ssl.create_default_context()

        if use_ssl:
            return smtplib.SMTP_SSL(
                smtp_host,
                smtp_port,
                timeout=30,
                context=context,
            )

        return smtplib.SMTP(
            smtp_host,
            smtp_port,
            timeout=30,
        )

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

        subject, text_body, html_body = (
            self._build_content(
                db,
                user_id=user_id,
                email=email,
                purpose=purpose,
                verification_method=(
                    verification_method
                ),
                otp=otp,
                link_token=link_token,
                otp_expiration_minutes=(
                    otp_expiration_minutes
                ),
                email_link_expiration_minutes=(
                    email_link_expiration_minutes
                ),
            )
        )

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = (
            f"{from_name} <{from_email}>"
        )
        message["To"] = email

        message.set_content(
            text_body
        )

        message.add_alternative(
            html_body,
            subtype="html",
        )

        smtp_username = str(
            getattr(
                settings,
                "SMTP_USERNAME",
                "",
            )
        ).strip()

        smtp_password = str(
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

        context = ssl.create_default_context()
        server = self._smtp_connection()

        try:
            if use_tls and not use_ssl:
                server.starttls(
                    context=context
                )

            if smtp_username:
                server.login(
                    smtp_username,
                    smtp_password,
                )

            server.send_message(
                message
            )

        finally:
            try:
                server.quit()
            except Exception:
                pass

        logger.info(
            "Account verification email sent.",
            extra={
                "user_id": user_id,
                "purpose": purpose,
                "verification_method": (
                    verification_method
                ),
            },
        )


account_verification_email_service = (
    AccountVerificationEmailService()
)