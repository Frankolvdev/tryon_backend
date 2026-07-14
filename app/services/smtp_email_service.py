import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.common.enums import IntegrationProvider
from app.common.exceptions import ConflictException
from app.services.integration_service import integration_service


class SMTPEmailService:
    def _get_config(self, db: Session):
        config = integration_service.get_config(db, IntegrationProvider.SMTP)

        if not config.is_enabled:
            raise ConflictException("SMTP integration is disabled.")

        parsed_config = integration_service._parse_json(config.config_json)

        host = parsed_config.get("host")
        port = int(parsed_config.get("port") or 587)
        use_tls = bool(parsed_config.get("use_tls", True))
        from_email = parsed_config.get("from_email")
        from_name = parsed_config.get("from_name") or "AI Try-On Platform"

        if not host:
            raise ConflictException("SMTP host is not configured.")

        if not from_email:
            raise ConflictException("SMTP from_email is not configured.")

        if not config.api_key:
            raise ConflictException("SMTP username is not configured.")

        if not config.api_secret:
            raise ConflictException("SMTP password is not configured.")

        return {
            "host": host,
            "port": port,
            "use_tls": use_tls,
            "username": config.api_key,
            "password": config.api_secret,
            "from_email": from_email,
            "from_name": from_name,
        }

    def health_check(self, db: Session) -> dict:
        smtp_config = self._get_config(db)

        with smtplib.SMTP(smtp_config["host"], smtp_config["port"], timeout=15) as server:
            if smtp_config["use_tls"]:
                server.starttls()

            server.login(
                smtp_config["username"],
                smtp_config["password"],
            )

        return {
            "healthy": True,
            "host": smtp_config["host"],
            "port": smtp_config["port"],
            "use_tls": smtp_config["use_tls"],
            "from_email": smtp_config["from_email"],
        }

    def send_email(
        self,
        db: Session,
        *,
        to_email: str,
        subject: str,
        body: str,
    ) -> dict:
        smtp_config = self._get_config(db)

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = f"{smtp_config['from_name']} <{smtp_config['from_email']}>"
        message["To"] = to_email
        message.set_content(body)

        with smtplib.SMTP(smtp_config["host"], smtp_config["port"], timeout=30) as server:
            if smtp_config["use_tls"]:
                server.starttls()

            server.login(
                smtp_config["username"],
                smtp_config["password"],
            )

            server.send_message(message)

        return {
            "sent": True,
            "to_email": to_email,
            "subject": subject,
        }


smtp_email_service = SMTPEmailService()