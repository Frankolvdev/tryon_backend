import logging

from sqlalchemy.orm import Session

from app.common.account_security_enums import (
    AccountVerificationPurpose,
)
from app.common.exceptions import (
    ConflictException,
)
from app.common.time import utc_now
from app.core.security import (
    hash_password,
)
from app.repositories.account_security_repository import (
    account_security_repository,
)
from app.schemas.password_recovery import (
    PasswordRecoveryConfirmResponse,
    PasswordRecoveryRequestResponse,
)
from app.services.account_security_service import (
    account_security_service,
)
from app.services.auth_service import (
    auth_service,
)


logger = logging.getLogger(
    "app.password_recovery"
)


class PasswordRecoveryService:
    GENERIC_REQUEST_MESSAGE = (
        "If an account exists for this email, "
        "password recovery instructions "
        "will be sent."
    )

    def request_recovery(
        self,
        db: Session,
        *,
        email: str,
        requested_ip: str | None,
        user_agent: str | None,
    ) -> PasswordRecoveryRequestResponse:
        _, _, verification_response = (
            account_security_service
            .create_challenge(
                db,
                email=email,
                purpose=(
                    AccountVerificationPurpose
                    .PASSWORD_RESET
                    .value
                ),
                requested_ip=requested_ip,
                user_agent=user_agent,
            )
        )

        return PasswordRecoveryRequestResponse(
            success=True,
            message=self.GENERIC_REQUEST_MESSAGE,
            verification_method=(
                verification_response
                .verification_method
            ),
            challenge_id=(
                verification_response
                .challenge_id
            ),
            expires_at=(
                verification_response
                .expires_at
            ),
            debug_otp=(
                verification_response
                .debug_otp
            ),
            debug_link_token=(
                verification_response
                .debug_link_token
            ),
        )

    def confirm_recovery(
        self,
        db: Session,
        *,
        email: str,
        otp: str | None,
        token: str | None,
        new_password: str,
        requested_ip: str | None,
        user_agent: str | None,
    ) -> PasswordRecoveryConfirmResponse:
        normalized_email = (
            email.strip().lower()
        )

        if not otp and not token:
            raise ConflictException(
                "OTP or verification token "
                "is required."
            )

        verification_result = (
            account_security_service
            .confirm_challenge(
                db,
                email=normalized_email,
                purpose=(
                    AccountVerificationPurpose
                    .PASSWORD_RESET
                    .value
                ),
                otp=otp,
                token=token,
                requested_ip=requested_ip,
                user_agent=user_agent,
            )
        )

        if not verification_result.verified:
            raise ConflictException(
                "Password recovery verification "
                "was not completed."
            )

        user = (
            account_security_repository
            .get_user_by_email(
                db,
                email=normalized_email,
            )
        )

        if user is None:
            raise ConflictException(
                "Password recovery could not "
                "be completed."
            )

        changed_at = utc_now()

        user.hashed_password = (
            hash_password(
                new_password
            )
        )

        db.add(user)

        security = (
            account_security_service
            .get_or_create_user_security(
                db,
                user_id=user.id,
            )
        )

        security.password_changed_at = (
            changed_at
        )

        security.failed_login_attempts = 0
        security.locked_until = None

        db.add(security)
        db.commit()

        revoked_sessions = (
            auth_service
            .revoke_all_user_sessions(
                db,
                user_id=user.id,
            )
        )

        try:
            from app.services.activity_service import (
                activity_service,
            )

            activity_service.create_log(
                db,
                user_id=user.id,
                action="password_recovered",
                description=(
                    "User recovered the account "
                    "password successfully."
                ),
                ip_address=requested_ip,
                user_agent=user_agent,
            )

        except Exception:
            logger.exception(
                "Could not record password "
                "recovery activity.",
                extra={
                    "user_id": user.id,
                },
            )

        try:
            from app.services.localized_user_notification_service import (
                localized_user_notification_service,
            )

            (
                localized_user_notification_service
                .create_for_user(
                    db,
                    user_id=user.id,
                    title_key=(
                        "account.password."
                        "changed.title"
                    ),
                    message_key=(
                        "account.password."
                        "changed.message"
                    ),
                    title_default=(
                        "Password changed"
                    ),
                    message_default=(
                        "Your account password "
                        "was changed successfully."
                    ),
                    notification_type="success",
                    priority="high",
                    source="security",
                    event_type=(
                        "password_recovered"
                    ),
                    action_url="/account/security",
                    action_label_key=(
                        "common.view_details"
                    ),
                    action_label_default=(
                        "View security"
                    ),
                    entity_type="user",
                    entity_id=user.id,
                )
            )

        except Exception:
            logger.exception(
                "Could not create password "
                "recovery notification.",
                extra={
                    "user_id": user.id,
                },
            )

        logger.info(
            "Password recovered successfully.",
            extra={
                "user_id": user.id,
                "revoked_sessions": (
                    revoked_sessions
                ),
            },
        )

        return PasswordRecoveryConfirmResponse(
            success=True,
            message=(
                "Password changed successfully. "
                "All active sessions were closed."
            ),
            revoked_sessions=revoked_sessions,
            password_changed_at=changed_at,
        )


password_recovery_service = (
    PasswordRecoveryService()
)