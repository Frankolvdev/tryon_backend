from sqlalchemy.orm import Session

from app.common.exceptions import (
    ForbiddenException,
)
from app.services.account_security_service import (
    account_security_service,
)
from app.services.disposable_email_service import (
    disposable_email_service,
)
from app.services.registration_limit_service import (
    registration_limit_service,
)
from app.services.turnstile_service import (
    turnstile_service,
)


class RegistrationSecurityService:
    def validate_before_registration(
        self,
        db: Session,
        *,
        email: str,
        turnstile_token: str | None,
        ip_address: str | None,
        device_id: str | None,
    ) -> None:
        config = (
            account_security_service
            .get_or_create_settings(db)
        )

        if not config.registration_enabled:
            raise ForbiddenException(
                "Registration is currently disabled."
            )

        if (
            config.block_disposable_email
            and disposable_email_service
            .is_disposable(email)
        ):
            raise ForbiddenException(
                "Temporary email addresses "
                "are not allowed."
            )

        try:
            registration_limit_service.check(
                ip_address=ip_address,
                device_id=device_id,
                max_per_ip=(
                    config
                    .max_accounts_per_ip_per_day
                ),
                max_per_device=(
                    config
                    .max_registrations_per_device_per_day
                ),
            )

        except PermissionError as error:
            raise ForbiddenException(
                "The daily registration limit "
                "has been reached."
            ) from error

        if config.turnstile_enabled:
            turnstile_service.verify(
                token=turnstile_token,
                remote_ip=ip_address,
            )

    def record_successful_registration(
        self,
        *,
        ip_address: str | None,
        device_id: str | None,
    ) -> None:
        registration_limit_service.register_success(
            ip_address=ip_address,
            device_id=device_id,
        )


registration_security_service = (
    RegistrationSecurityService()
)