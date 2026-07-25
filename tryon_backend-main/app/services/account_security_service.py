import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from app.common.account_security_enums import (
    AccountVerificationChallengeStatus,
    AccountVerificationMethod,
    AccountVerificationPurpose,
)
from app.common.exceptions import (
    ConflictException,
    NotFoundException,
)
from app.common.time import utc_now
from app.core.config import settings
from app.models.account_security_setting import (
    AccountSecuritySetting,
)
from app.models.account_verification_challenge import (
    AccountVerificationChallenge,
)
from app.models.user_account_security import (
    UserAccountSecurity,
)
from app.repositories.account_security_repository import (
    account_security_repository,
)
from app.schemas.account_security import (
    AccountSecuritySettingsResponse,
    AccountSecuritySettingsUpdate,
    AccountVerificationChallengeListResponse,
    AccountVerificationChallengeResponse,
    AccountVerificationConfirmResponse,
    AccountVerificationRequestResponse,
    AccountVerificationStatusResponse,
    AdminAccountVerificationResponse,
)
from app.services.account_verification_email_service import (
    account_verification_email_service,
)


logger = logging.getLogger(
    "app.account_security"
)


@dataclass
class GeneratedVerificationSecrets:
    otp: str | None
    link_token: str | None


class AccountSecurityService:
    GENERIC_REQUEST_MESSAGE = (
        "If the account exists, verification "
        "instructions will be sent."
    )

    def _secret_key(self) -> str:
        secret_key = getattr(
            settings,
            "SECRET_KEY",
            None,
        )

        if not secret_key:
            secret_key = getattr(
                settings,
                "JWT_SECRET_KEY",
                None,
            )

        if not secret_key:
            raise RuntimeError(
                "SECRET_KEY or JWT_SECRET_KEY "
                "must be configured."
            )

        return str(secret_key)

    def _normalize_email(
        self,
        email: str,
    ) -> str:
        return email.strip().lower()

    def _hash_secret(
        self,
        value: str,
    ) -> str:
        return hmac.new(
            self._secret_key().encode(
                "utf-8"
            ),
            value.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _verify_secret(
        self,
        raw_value: str,
        stored_hash: str | None,
    ) -> bool:
        if not stored_hash:
            return False

        calculated = self._hash_secret(
            raw_value
        )

        return hmac.compare_digest(
            calculated,
            stored_hash,
        )

    def _generate_otp(
        self,
        length: int,
    ) -> str:
        return "".join(
            secrets.choice(
                "0123456789"
            )
            for _ in range(length)
        )

    def _generate_link_token(
        self,
    ) -> str:
        return secrets.token_urlsafe(
            48
        )

    def _generic_response(
        self,
        *,
        verification_method: str,
    ) -> AccountVerificationRequestResponse:
        return AccountVerificationRequestResponse(
            success=True,
            message=self.GENERIC_REQUEST_MESSAGE,
            verification_method=(
                verification_method
            ),
        )

    def get_or_create_settings(
        self,
        db: Session,
    ) -> AccountSecuritySetting:
        config = (
            account_security_repository
            .get_settings(db)
        )

        if config is not None:
            return config

        config = AccountSecuritySetting(
            id=1,
        )

        db.add(config)
        db.commit()
        db.refresh(config)

        return config

    def get_settings_response(
        self,
        db: Session,
    ) -> AccountSecuritySettingsResponse:
        config = self.get_or_create_settings(
            db
        )

        return (
            AccountSecuritySettingsResponse
            .model_validate(config)
        )

    def update_settings(
        self,
        db: Session,
        *,
        data: AccountSecuritySettingsUpdate,
    ) -> AccountSecuritySettingsResponse:
        config = self.get_or_create_settings(
            db
        )

        for field, value in (
            data.model_dump().items()
        ):
            setattr(
                config,
                field,
                value,
            )

        if not config.verification_required:
            config.verification_method = (
                AccountVerificationMethod
                .DISABLED
                .value
            )

        elif (
            config.verification_method
            == AccountVerificationMethod
            .DISABLED
            .value
        ):
            config.verification_method = (
                AccountVerificationMethod
                .OTP_AND_EMAIL_LINK
                .value
            )

        db.add(config)
        db.commit()
        db.refresh(config)

        return (
            AccountSecuritySettingsResponse
            .model_validate(config)
        )

    def get_or_create_user_security(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> UserAccountSecurity:
        security = (
            account_security_repository
            .get_user_security(
                db,
                user_id=user_id,
            )
        )

        if security is not None:
            return security

        config = self.get_or_create_settings(
            db
        )

        verification_required = (
            config.verification_required
            and config.verification_method
            != AccountVerificationMethod
            .DISABLED
            .value
        )

        security = UserAccountSecurity(
            user_id=user_id,
            account_status=(
                "pending_verification"
                if verification_required
                else "active"
            ),
            verification_required=(
                verification_required
            ),
            email_verified=(
                not verification_required
            ),
            email_verified_at=(
                None
                if verification_required
                else utc_now()
            ),
        )

        db.add(security)
        db.commit()
        db.refresh(security)

        return security

    def get_status(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> AccountVerificationStatusResponse:
        security = (
            self.get_or_create_user_security(
                db,
                user_id=user_id,
            )
        )

        return AccountVerificationStatusResponse(
            user_id=user_id,
            account_status=(
                security.account_status
            ),
            verification_required=(
                security.verification_required
            ),
            email_verified=(
                security.email_verified
            ),
            email_verified_at=(
                security.email_verified_at
            ),
            terms_accepted=(
                security.terms_accepted
            ),
            age_confirmed=(
                security.age_confirmed
            ),
            locked_until=(
                security.locked_until
            ),
        )

    def create_challenge(
        self,
        db: Session,
        *,
        email: str,
        purpose: str,
        requested_ip: str | None,
        user_agent: str | None,
    ) -> tuple[
        AccountVerificationChallenge | None,
        GeneratedVerificationSecrets,
        AccountVerificationRequestResponse,
    ]:
        normalized_email = (
            self._normalize_email(email)
        )

        config = self.get_or_create_settings(
            db
        )

        method = config.verification_method

        if (
            not config.verification_required
            or method
            == AccountVerificationMethod
            .DISABLED
            .value
        ):
            return (
                None,
                GeneratedVerificationSecrets(
                    otp=None,
                    link_token=None,
                ),
                AccountVerificationRequestResponse(
                    success=True,
                    message=(
                        "Account verification "
                        "is disabled."
                    ),
                    verification_method=(
                        AccountVerificationMethod
                        .DISABLED
                        .value
                    ),
                ),
            )

        user = (
            account_security_repository
            .get_user_by_email(
                db,
                email=normalized_email,
            )
        )

        if user is None:
            return (
                None,
                GeneratedVerificationSecrets(
                    otp=None,
                    link_token=None,
                ),
                self._generic_response(
                    verification_method=method,
                ),
            )

        user_security = (
            self.get_or_create_user_security(
                db,
                user_id=user.id,
            )
        )

        if (
            purpose
            == AccountVerificationPurpose
            .REGISTRATION
            .value
            and user_security.email_verified
        ):
            return (
                None,
                GeneratedVerificationSecrets(
                    otp=None,
                    link_token=None,
                ),
                self._generic_response(
                    verification_method=method,
                ),
            )

        now = utc_now()

        active_challenge = (
            account_security_repository
            .get_active_challenge(
                db,
                email=normalized_email,
                purpose=purpose,
            )
        )

        if active_challenge is not None:
            next_allowed_at = (
                active_challenge.last_sent_at
                + timedelta(
                    seconds=(
                        config
                        .otp_resend_cooldown_seconds
                    )
                )
            )

            if next_allowed_at > now:
                remaining_seconds = max(
                    1,
                    int(
                        (
                            next_allowed_at
                            - now
                        ).total_seconds()
                    ),
                )

                raise ConflictException(
                    "Please wait "
                    f"{remaining_seconds} second(s) "
                    "before requesting another "
                    "verification message."
                )

        requests_in_last_hour = (
            account_security_repository
            .count_challenges_since(
                db,
                email=normalized_email,
                purpose=purpose,
                created_from=(
                    now
                    - timedelta(hours=1)
                ),
            )
        )

        if (
            requests_in_last_hour
            >= config.otp_max_resends_per_hour
        ):
            raise ConflictException(
                "Maximum verification requests "
                "per hour reached."
            )

        (
            account_security_repository
            .cancel_pending_challenges(
                db,
                email=normalized_email,
                purpose=purpose,
            )
        )

        otp = None
        link_token = None

        if method in {
            AccountVerificationMethod
            .OTP
            .value,
            AccountVerificationMethod
            .OTP_AND_EMAIL_LINK
            .value,
        }:
            otp = self._generate_otp(
                config.otp_length
            )

        if method in {
            AccountVerificationMethod
            .EMAIL_LINK
            .value,
            AccountVerificationMethod
            .OTP_AND_EMAIL_LINK
            .value,
        }:
            link_token = (
                self._generate_link_token()
            )

        expiration_minutes = max(
            config.otp_expiration_minutes,
            config.email_link_expiration_minutes,
        )

        challenge = (
            AccountVerificationChallenge(
                user_id=user.id,
                email=normalized_email,
                purpose=purpose,
                verification_method=method,
                status=(
                    AccountVerificationChallengeStatus
                    .PENDING
                    .value
                ),
                otp_hash=(
                    self._hash_secret(otp)
                    if otp
                    else None
                ),
                link_token_hash=(
                    self._hash_secret(
                        link_token
                    )
                    if link_token
                    else None
                ),
                attempt_count=0,
                max_attempts=(
                    config.otp_max_attempts
                ),
                resend_count=(
                    requests_in_last_hour
                ),
                requested_ip=requested_ip,
                user_agent=user_agent,
                expires_at=(
                    now
                    + timedelta(
                        minutes=(
                            expiration_minutes
                        )
                    )
                ),
                last_sent_at=now,
            )
        )

        db.add(challenge)
        db.commit()
        db.refresh(challenge)

        try:
            (
                account_verification_email_service
                .send_verification(
                    db,
                    user_id=user.id,
                    email=normalized_email,
                    purpose=purpose,
                    verification_method=method,
                    otp=otp,
                    link_token=link_token,
                    otp_expiration_minutes=(
                        config
                        .otp_expiration_minutes
                    ),
                    email_link_expiration_minutes=(
                        config
                        .email_link_expiration_minutes
                    ),
                )
            )

        except Exception as error:
            logger.exception(
                "Could not send account "
                "verification email.",
                extra={
                    "challenge_id": (
                        challenge.id
                    ),
                    "user_id": user.id,
                    "purpose": purpose,
                },
            )

            if not bool(
                getattr(
                    settings,
                    "DEBUG",
                    False,
                )
            ):
                challenge.status = (
                    AccountVerificationChallengeStatus
                    .CANCELLED
                    .value
                )

                db.add(challenge)
                db.commit()

                raise ConflictException(
                    "The verification email "
                    "could not be sent."
                ) from error

        debug_enabled = bool(
            getattr(
                settings,
                "DEBUG",
                False,
            )
        )

        response = (
            AccountVerificationRequestResponse(
                success=True,
                message=(
                    self.GENERIC_REQUEST_MESSAGE
                ),
                verification_method=method,
                challenge_id=(
                    challenge.id
                    if debug_enabled
                    else None
                ),
                expires_at=(
                    challenge.expires_at
                ),
                debug_otp=(
                    otp
                    if debug_enabled
                    else None
                ),
                debug_link_token=(
                    link_token
                    if debug_enabled
                    else None
                ),
            )
        )

        return (
            challenge,
            GeneratedVerificationSecrets(
                otp=otp,
                link_token=link_token,
            ),
            response,
        )

    def _complete_registration_verification(
        self,
        db: Session,
        *,
        challenge: AccountVerificationChallenge,
        requested_ip: str | None,
        user_agent: str | None,
    ) -> UserAccountSecurity:
        if challenge.user_id is None:
            raise NotFoundException(
                "The verification challenge "
                "has no associated user."
            )

        user = (
            account_security_repository
            .get_user_by_id(
                db,
                user_id=challenge.user_id,
            )
        )

        if user is None:
            raise NotFoundException(
                "User not found."
            )

        from app.services.user_service import (
            user_service,
        )

        verified_user = (
            user_service.mark_email_verified(
                db,
                email=user.email,
            )
        )

        if verified_user is None:
            raise NotFoundException(
                "User not found."
            )

        security = (
            self.get_or_create_user_security(
                db,
                user_id=user.id,
            )
        )

        security.email_verified = True

        if security.email_verified_at is None:
            security.email_verified_at = (
                utc_now()
            )

        security.account_status = "active"
        security.failed_login_attempts = 0
        security.locked_until = None

        db.add(security)

        (
            account_security_repository
            .cancel_pending_challenges(
                db,
                email=user.email,
                purpose=(
                    AccountVerificationPurpose
                    .REGISTRATION
                    .value
                ),
            )
        )

        challenge.status = (
            AccountVerificationChallengeStatus
            .VERIFIED
            .value
        )

        challenge.verified_at = (
            challenge.verified_at
            or utc_now()
        )

        challenge.consumed_at = (
            challenge.consumed_at
            or utc_now()
        )

        db.add(challenge)
        db.commit()
        db.refresh(security)

        try:
            from app.services.activity_service import (
                activity_service,
            )

            activity_service.create_log(
                db,
                user_id=user.id,
                action="email_verified",
                description=(
                    "User verified the account "
                    "email successfully."
                ),
                ip_address=requested_ip,
                user_agent=user_agent,
            )

        except Exception:
            logger.exception(
                "Could not create verification "
                "activity log.",
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
                        "account.verification."
                        "completed.title"
                    ),
                    message_key=(
                        "account.verification."
                        "completed.message"
                    ),
                    title_default=(
                        "Account verified"
                    ),
                    message_default=(
                        "Your account was verified "
                        "successfully."
                    ),
                    notification_type="success",
                    priority="normal",
                    source="security",
                    event_type=(
                        "account_verified"
                    ),
                    action_url="/account",
                    action_label_key=(
                        "common.view_details"
                    ),
                    action_label_default=(
                        "View account"
                    ),
                    entity_type="user",
                    entity_id=user.id,
                )
            )

        except Exception:
            logger.exception(
                "Could not create account "
                "verification notification.",
                extra={
                    "user_id": user.id,
                },
            )

        return security

    def confirm_challenge(
        self,
        db: Session,
        *,
        email: str,
        purpose: str,
        otp: str | None,
        token: str | None,
        requested_ip: str | None = None,
        user_agent: str | None = None,
    ) -> AccountVerificationConfirmResponse:
        normalized_email = (
            self._normalize_email(email)
        )

        if not otp and not token:
            raise ConflictException(
                "OTP or verification token "
                "is required."
            )

        challenge = (
            account_security_repository
            .get_active_challenge(
                db,
                email=normalized_email,
                purpose=purpose,
            )
        )

        if challenge is None:
            raise NotFoundException(
                "Verification challenge "
                "not found."
            )

        now = utc_now()

        if challenge.expires_at <= now:
            challenge.status = (
                AccountVerificationChallengeStatus
                .EXPIRED
                .value
            )

            db.add(challenge)
            db.commit()

            raise ConflictException(
                "The verification code or "
                "link has expired."
            )

        if (
            challenge.attempt_count
            >= challenge.max_attempts
        ):
            challenge.status = (
                AccountVerificationChallengeStatus
                .BLOCKED
                .value
            )

            db.add(challenge)
            db.commit()

            raise ConflictException(
                "Maximum verification "
                "attempts reached."
            )

        challenge.attempt_count += 1

        otp_valid = bool(
            otp
            and self._verify_secret(
                otp.strip(),
                challenge.otp_hash,
            )
        )

        token_valid = bool(
            token
            and self._verify_secret(
                token.strip(),
                challenge.link_token_hash,
            )
        )

        if not otp_valid and not token_valid:
            if (
                challenge.attempt_count
                >= challenge.max_attempts
            ):
                challenge.status = (
                    AccountVerificationChallengeStatus
                    .BLOCKED
                    .value
                )

            db.add(challenge)
            db.commit()

            raise ConflictException(
                "Invalid verification code "
                "or token."
            )

        challenge.status = (
            AccountVerificationChallengeStatus
            .VERIFIED
            .value
        )

        challenge.verified_at = now
        challenge.consumed_at = now

        db.add(challenge)
        db.commit()
        db.refresh(challenge)

        user_id = challenge.user_id
        account_status = None
        email_verified_at = None

        if (
            purpose
            == AccountVerificationPurpose
            .REGISTRATION
            .value
        ):
            security = (
                self._complete_registration_verification(
                    db,
                    challenge=challenge,
                    requested_ip=requested_ip,
                    user_agent=user_agent,
                )
            )

            account_status = (
                security.account_status
            )

            email_verified_at = (
                security.email_verified_at
            )

        return AccountVerificationConfirmResponse(
            success=True,
            verified=True,
            message=(
                "The account was verified "
                "successfully."
            ),
            user_id=user_id,
            account_status=account_status,
            email_verified_at=(
                email_verified_at
            ),
        )

    def admin_verify_user(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> AdminAccountVerificationResponse:
        user = (
            account_security_repository
            .get_user_by_id(
                db,
                user_id=user_id,
            )
        )

        if user is None:
            raise NotFoundException(
                "User not found."
            )

        from app.services.user_service import (
            user_service,
        )

        verified_user = (
            user_service.mark_email_verified(
                db,
                email=user.email,
            )
        )

        if verified_user is None:
            raise NotFoundException(
                "User not found."
            )

        security = (
            self.get_or_create_user_security(
                db,
                user_id=user.id,
            )
        )

        security.email_verified = True
        security.email_verified_at = (
            security.email_verified_at
            or utc_now()
        )

        security.account_status = "active"
        security.failed_login_attempts = 0
        security.locked_until = None

        (
            account_security_repository
            .cancel_pending_challenges(
                db,
                email=user.email,
                purpose=(
                    AccountVerificationPurpose
                    .REGISTRATION
                    .value
                ),
            )
        )

        db.add(security)
        db.commit()
        db.refresh(security)

        return AdminAccountVerificationResponse(
            success=True,
            user_id=user.id,
            email=user.email,
            account_status=(
                security.account_status
            ),
            email_verified=(
                security.email_verified
            ),
            email_verified_at=(
                security.email_verified_at
            ),
            message=(
                "The account was verified "
                "manually."
            ),
        )

    def admin_resend_verification(
        self,
        db: Session,
        *,
        user_id: int,
        requested_ip: str | None,
        user_agent: str | None,
    ) -> AccountVerificationRequestResponse:
        user = (
            account_security_repository
            .get_user_by_id(
                db,
                user_id=user_id,
            )
        )

        if user is None:
            raise NotFoundException(
                "User not found."
            )

        security = (
            self.get_or_create_user_security(
                db,
                user_id=user.id,
            )
        )

        if security.email_verified:
            raise ConflictException(
                "The account is already verified."
            )

        _, _, response = self.create_challenge(
            db,
            email=user.email,
            purpose=(
                AccountVerificationPurpose
                .REGISTRATION
                .value
            ),
            requested_ip=requested_ip,
            user_agent=user_agent,
        )

        return response

    def admin_cancel_verification(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> AdminAccountVerificationResponse:
        user = (
            account_security_repository
            .get_user_by_id(
                db,
                user_id=user_id,
            )
        )

        if user is None:
            raise NotFoundException(
                "User not found."
            )

        (
            account_security_repository
            .cancel_pending_challenges(
                db,
                email=user.email,
                purpose=(
                    AccountVerificationPurpose
                    .REGISTRATION
                    .value
                ),
            )
        )

        security = (
            self.get_or_create_user_security(
                db,
                user_id=user.id,
            )
        )

        db.commit()

        return AdminAccountVerificationResponse(
            success=True,
            user_id=user.id,
            email=user.email,
            account_status=(
                security.account_status
            ),
            email_verified=(
                security.email_verified
            ),
            email_verified_at=(
                security.email_verified_at
            ),
            message=(
                "Pending verification "
                "challenges were cancelled."
            ),
        )

    def list_challenges(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        email: str | None = None,
        purpose: str | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> AccountVerificationChallengeListResponse:
        items = (
            account_security_repository
            .list_challenges(
                db,
                user_id=user_id,
                email=email,
                purpose=purpose,
                status=status,
                skip=skip,
                limit=limit,
            )
        )

        total = (
            account_security_repository
            .count_challenges(
                db,
                user_id=user_id,
                email=email,
                purpose=purpose,
                status=status,
            )
        )

        return (
            AccountVerificationChallengeListResponse(
                items=[
                    AccountVerificationChallengeResponse
                    .model_validate(item)
                    for item in items
                ],
                total=total,
                skip=skip,
                limit=limit,
            )
        )


account_security_service = (
    AccountSecurityService()
)