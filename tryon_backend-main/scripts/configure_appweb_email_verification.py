"""Asegura la política real de verificación de correo para App Web.

Ejecutar desde la raíz de tryon_backend:

    python scripts/configure_appweb_email_verification.py
"""

from __future__ import annotations

from app.db.database import SessionLocal
from app.services.account_security_service import account_security_service


def main() -> None:
    db = SessionLocal()
    try:
        settings = account_security_service.get_or_create_settings(db)

        settings.registration_enabled = True
        settings.verification_required = True
        settings.verification_method = "email_link"
        settings.allow_login_before_verification = False
        settings.otp_resend_cooldown_seconds = max(
            60,
            int(settings.otp_resend_cooldown_seconds or 0),
        )
        settings.otp_max_resends_per_hour = max(
            1,
            min(int(settings.otp_max_resends_per_hour or 5), 5),
        )
        settings.email_link_expiration_minutes = max(
            30,
            int(settings.email_link_expiration_minutes or 60),
        )

        db.add(settings)
        db.commit()
        db.refresh(settings)

        print("Política de verificación configurada correctamente:")
        print(f"  registration_enabled={settings.registration_enabled}")
        print(f"  verification_required={settings.verification_required}")
        print(f"  verification_method={settings.verification_method}")
        print(
            "  allow_login_before_verification="
            f"{settings.allow_login_before_verification}"
        )
        print(
            "  otp_resend_cooldown_seconds="
            f"{settings.otp_resend_cooldown_seconds}"
        )
        print(
            "  otp_max_resends_per_hour="
            f"{settings.otp_max_resends_per_hour}"
        )
        print(
            "  email_link_expiration_minutes="
            f"{settings.email_link_expiration_minutes}"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
