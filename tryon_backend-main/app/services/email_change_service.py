import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from sqlalchemy.orm import Session

from app.common.account_security_enums import (
    AccountVerificationMethod,
)
from app.common.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.common.time import utc_now
from app.core.config import settings
from app.core.security import verify_password
from app.models.email_change_request import (
    EmailChangeRequest,
)
from app.models.user import User
from app.repositories.email_change_repository import (
    email_change_repository,
)
from app.repositories.user_repository import (
    user_repository,
)
from app.schemas.email_change import (
    EmailChangeCancelResponse,
    EmailChangeConfirmResponse,
    EmailChangeRequestListResponse,
    EmailChangeRequestResponse,
)
from app.services.account_security_service import (
    account_security_service,
)
from app.services.auth_service import auth_service
from app.services.email_change_email_service import (
    email_change_email_service,
)


logger = logging.getLogger(
    "app.email_change"
)


class EmailChangeService:
    def _secret_key(self) -> str:
        value = getattr(
            settings,
            "SECRET_KEY",
            None,
        ) or getattr(
            settings,
            "JWT_SECRET_KEY",
            None,
        )

        if not value:
            raise RuntimeError(
                "SECRET_KEY or JWT_SECRET_KEY "
                "must be configured."
            )

        return str(value)

    def _hash(
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

    def _matches(
        self,
        raw_value: str,
        stored_hash: str | None,
    ) -> bool:
        if not stored_hash:
            return False

        return hmac.compare_digest(
            self._hash(raw_value),
            stored_hash,
        )

    def _otp(
        self,
        length: int,
    ) -> str:
        return "".join(
            secrets.choice(
                "0123456789"
            )
            for _ in range(length)
        )

    def request_change(
        self,
        db: Session,
        *,
        user: User,
        new_email: str,
        current_password: str,
        requested_ip: str | None,
        user_agent: str | None,
    ) -> EmailChangeRequestResponse:
        normalized_email = (
            new_email.strip().lower()
        )

        if normalized_email == user.email.lower():
            raise ConflictException(
                "The new email must be different."
            )

        if user.hashed_password is None:
            raise ForbiddenException(
                "Password confirmation is not "
                "available for this account."
            )

        if not verify_password(
            current_password,
            user.hashed_password,
        ):
            raise ForbiddenException(
                "Current password is incorrect."
            )

        existing = user_repository.get_by_email(
            db,
            normalized_email,
        )

        if existing is not None:
            raise ConflictException(
                "This email address is already in use."
            )

        config = (
            account_security_service
            .get_or_create_settings(db)
        )

        method = config.verification_method

        if method == (
            AccountVerificationMethod
            .DISABLED
            .value
        ):
            method = (
                AccountVerificationMethod
                .OTP_AND_EMAIL_LINK
                .value
            )

        now = utc_now()

        current_request = (
            email_change_repository
            .get_pending_for_user(
                db,
                user_id=user.id,
            )
        )

        if current_request is not None:
            next_allowed = (
                current_request.last_sent_at
                + timedelta(
                    seconds=(
                        config
                        .otp_resend_cooldown_seconds
                    )
                )
            )

            if next_allowed > now:
                seconds = max(
                    1,
                    int(
                        (
                            next_allowed
                            - now
                        ).total_seconds()
                    ),
                )

                raise ConflictException(
                    "Please wait "
                    f"{seconds} second(s) before "
                    "requesting another email change."
                )

        requests_last_hour = (
            email_change_repository
            .count_since(
                db,
                user_id=user.id,
                created_from=(
                    now
                    - timedelta(hours=1)
                ),
            )
        )

        if (
            requests_last_hour
            >= config.otp_max_resends_per_hour
        ):
            raise ConflictException(
                "Maximum email change requests "
                "per hour reached."
            )

        email_change_repository.cancel_pending(
            db,
            user_id=user.id,
        )

        otp = None
        token = None

        if method in {
            AccountVerificationMethod.OTP.value,
            AccountVerificationMethod
            .OTP_AND_EMAIL_LINK
            .value,
        }:
            otp = self._otp(
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
            token = secrets.token_urlsafe(
                48
            )

        expiration_minutes = max(
            config.otp_expiration_minutes,
            config.email_link_expiration_minutes,
        )

        request_obj = EmailChangeRequest(
            user_id=user.id,
            current_email=user.email,
            new_email=normalized_email,
            verification_method=method,
            status="pending",
            otp_hash=(
                self._hash(otp)
                if otp
                else None
            ),
            link_token_hash=(
                self._hash(token)
                if token
                else None
            ),
            attempt_count=0,
            max_attempts=(
                config.otp_max_attempts
            ),
            resend_count=requests_last_hour,
            requested_ip=requested_ip,
            user_agent=user_agent,
            expires_at=(
                now
                + timedelta(
                    minutes=expiration_minutes
                )
            ),
            last_sent_at=now,
        )

        db.add(request_obj)
        db.commit()
        db.refresh(request_obj)

        try:
            email_change_email_service.send_new_email_verification(
                db,
                user_id=user.id,
                old_email=user.email,
                new_email=normalized_email,
                otp=otp,
                link_token=token,
                otp_expiration_minutes=(
                    config.otp_expiration_minutes
                ),
                link_expiration_minutes=(
                    config
                    .email_link_expiration_minutes
                ),
            )

        except Exception as error:
            logger.exception(
                "Could not send email change "
                "verification message.",
                extra={
                    "user_id": user.id,
                    "request_id": request_obj.id,
                },
            )

            if not bool(
                getattr(
                    settings,
                    "DEBUG",
                    False,
                )
            ):
                request_obj.status = "cancelled"
                request_obj.cancelled_at = (
                    utc_now()
                )

                db.add(request_obj)
                db.commit()

                raise ConflictException(
                    "The verification message "
                    "could not be sent."
                ) from error

        debug_enabled = bool(
            getattr(
                settings,
                "DEBUG",
                False,
            )
        )

        return EmailChangeRequestResponse(
            success=True,
            message=(
                "Verification instructions were "
                "sent to the new email address."
            ),
            request_id=(
                request_obj.id
                if debug_enabled
                else None
            ),
            verification_method=method,
            expires_at=request_obj.expires_at,
            debug_otp=(
                otp
                if debug_enabled
                else None
            ),
            debug_link_token=(
                token
                if debug_enabled
                else None
            ),
        )

    def confirm_change(
        self,
        db: Session,
        *,
        user: User,
        new_email: str,
        otp: str | None,
        token: str | None,
        requested_ip: str | None,
        user_agent: str | None,
    ) -> EmailChangeConfirmResponse:
        normalized_email = (
            new_email.strip().lower()
        )

        if not otp and not token:
            raise ConflictException(
                "OTP or verification token "
                "is required."
            )

        request_obj = (
            email_change_repository
            .get_pending_for_confirmation(
                db,
                user_id=user.id,
                new_email=normalized_email,
            )
        )

        if request_obj is None:
            raise NotFoundException(
                "Pending email change request "
                "not found."
            )

        now = utc_now()

        if request_obj.expires_at <= now:
            request_obj.status = "expired"

            db.add(request_obj)
            db.commit()

            raise ConflictException(
                "The verification code or link "
                "has expired."
            )

        if (
            request_obj.attempt_count
            >= request_obj.max_attempts
        ):
            request_obj.status = "blocked"

            db.add(request_obj)
            db.commit()

            raise ConflictException(
                "Maximum verification attempts "
                "reached."
            )

        request_obj.attempt_count += 1

        valid_otp = bool(
            otp
            and self._matches(
                otp.strip(),
                request_obj.otp_hash,
            )
        )

        valid_token = bool(
            token
            and self._matches(
                token.strip(),
                request_obj.link_token_hash,
            )
        )

        if not valid_otp and not valid_token:
            if (
                request_obj.attempt_count
                >= request_obj.max_attempts
            ):
                request_obj.status = "blocked"

            db.add(request_obj)
            db.commit()

            raise ConflictException(
                "Invalid verification code "
                "or token."
            )

        existing = user_repository.get_by_email(
            db,
            normalized_email,
        )

        if (
            existing is not None
            and existing.id != user.id
        ):
            request_obj.status = "cancelled"
            request_obj.cancelled_at = now

            db.add(request_obj)
            db.commit()

            raise ConflictException(
                "This email address is already in use."
            )

        old_email = user.email

        user.email = normalized_email
        user.is_verified = True

        request_obj.status = "verified"
        request_obj.verified_at = now

        security = (
            account_security_service
            .get_or_create_user_security(
                db,
                user_id=user.id,
            )
        )

        security.email_verified = True
        security.email_verified_at = now
        security.account_status = "active"

        db.add(user)
        db.add(security)
        db.add(request_obj)
        db.commit()
        db.refresh(user)

        revoked_sessions = (
            auth_service
            .revoke_all_user_sessions(
                db,
                user_id=user.id,
            )
        )

        try:
            email_change_email_service.send_old_email_notice(
                old_email=old_email,
                new_email=normalized_email,
            )

        except Exception:
            logger.exception(
                "Could not notify previous email.",
                extra={
                    "user_id": user.id,
                    "old_email": old_email,
                },
            )

        try:
            from app.services.activity_service import (
                activity_service,
            )

            activity_service.create_log(
                db,
                user_id=user.id,
                action="email_changed",
                description=(
                    "User changed the account "
                    "email address."
                ),
                ip_address=requested_ip,
                user_agent=user_agent,
            )

        except Exception:
            logger.exception(
                "Could not record email change "
                "activity.",
                extra={
                    "user_id": user.id,
                },
            )

        try:
            from app.services.localized_user_notification_service import (
                localized_user_notification_service,
            )

            localized_user_notification_service.create_for_user(
                db,
                user_id=user.id,
                title_key=(
                    "account.email_change."
                    "completed.title"
                ),
                message_key=(
                    "account.email_change."
                    "completed.message"
                ),
                title_default=(
                    "Email address changed"
                ),
                message_default=(
                    "Your account email address "
                    "was changed successfully."
                ),
                notification_type="success",
                priority="high",
                source="security",
                event_type="email_changed",
                action_url="/account/security",
                action_label_key=(
                    "common.view_details"
                ),
                action_label_default=(
                    "View security"
                ),
                entity_type="user",
                entity_id=user.id,
                metadata={
                    "old_email": old_email,
                    "new_email": normalized_email,
                },
            )

        except Exception:
            logger.exception(
                "Could not create email change "
                "notification.",
                extra={
                    "user_id": user.id,
                },
            )

        return EmailChangeConfirmResponse(
            success=True,
            message=(
                "Email address changed "
                "successfully. All active "
                "sessions were closed."
            ),
            user_id=user.id,
            old_email=old_email,
            new_email=normalized_email,
            revoked_sessions=revoked_sessions,
            changed_at=now,
        )

    def cancel_pending(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> EmailChangeCancelResponse:
        cancelled = (
            email_change_repository
            .cancel_pending(
                db,
                user_id=user_id,
            )
        )

        db.commit()

        return EmailChangeCancelResponse(
            success=True,
            cancelled_requests=cancelled,
            message=(
                "Pending email change requests "
                "were cancelled."
            ),
        )

    def list_requests(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        status: str | None = None,
        search: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> EmailChangeRequestListResponse:
        items = (
            email_change_repository
            .list_requests(
                db,
                user_id=user_id,
                status=status,
                search=search,
                skip=skip,
                limit=limit,
            )
        )

        total = (
            email_change_repository
            .count_requests(
                db,
                user_id=user_id,
                status=status,
                search=search,
            )
        )

        return EmailChangeRequestListResponse(
            items=items,
            total=total,
            skip=skip,
            limit=limit,
        )


email_change_service = EmailChangeService()