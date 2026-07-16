from datetime import timedelta
import hashlib
import secrets

from sqlalchemy.orm import Session

from app.common.exceptions import UnauthorizedException
from app.common.time import utc_now
from app.core.config import settings
from app.core.jwt import create_access_token
from app.core.security import verify_password
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.refresh_token_repository import (
    refresh_token_repository,
)
from app.repositories.user_repository import (
    user_repository,
)
from app.services.account_security_service import (
    account_security_service,
)
from app.services.admin_mfa_service import (
    admin_mfa_service,
)


class AuthService:
    MAX_FAILED_LOGIN_ATTEMPTS = 5
    LOGIN_LOCK_MINUTES = 15

    def _hash_refresh_token(
        self,
        refresh_token: str,
    ) -> str:
        return hashlib.sha256(
            refresh_token.encode("utf-8")
        ).hexdigest()

    def _generate_refresh_token(self) -> str:
        return secrets.token_urlsafe(64)

    def _record_failed_login(
        self,
        db: Session,
        *,
        user: User,
    ) -> None:
        security = (
            account_security_service
            .get_or_create_user_security(
                db,
                user_id=user.id,
            )
        )
        now = utc_now()

        if (
            security.locked_until is not None
            and security.locked_until <= now
        ):
            security.failed_login_attempts = 0
            security.locked_until = None

        security.failed_login_attempts += 1

        if (
            security.failed_login_attempts
            >= self.MAX_FAILED_LOGIN_ATTEMPTS
        ):
            security.locked_until = (
                now
                + timedelta(
                    minutes=self.LOGIN_LOCK_MINUTES
                )
            )

        db.add(security)
        db.commit()

    def _validate_account_access(
        self,
        db: Session,
        *,
        user: User,
    ):
        if not user.is_active:
            raise UnauthorizedException(
                "Invalid credentials."
            )

        security = (
            account_security_service
            .get_or_create_user_security(
                db,
                user_id=user.id,
            )
        )
        now = utc_now()

        if (
            security.locked_until is not None
            and security.locked_until > now
        ):
            raise UnauthorizedException(
                "The account is temporarily locked."
            )

        if security.account_status in {
            "suspended",
            "blocked",
            "deleted",
            "deleted_unverified",
        }:
            raise UnauthorizedException(
                "The account is not available."
            )

        account_settings = (
            account_security_service
            .get_or_create_settings(db)
        )
        verification_required = bool(
            security.verification_required
            and account_settings.verification_required
        )

        if (
            verification_required
            and not security.email_verified
            and not (
                account_settings
                .allow_login_before_verification
            )
        ):
            raise UnauthorizedException(
                "You must verify your email "
                "before signing in."
            )

        return security

    def _validate_mfa(
        self,
        db: Session,
        *,
        user: User,
        mfa_code: str | None,
    ) -> bool:
        required = admin_mfa_service.is_required(
            db,
            user=user,
        )
        enabled = admin_mfa_service.is_enabled(
            db,
            user_id=user.id,
        )

        if not required and not enabled:
            return False

        if required and not admin_mfa_service.totp_enabled(
            db,
            user=user,
        ):
            raise UnauthorizedException(
                "MFA is required but no MFA method "
                "is enabled for this account type."
            )

        if required and not enabled:
            return True

        if not mfa_code:
            raise UnauthorizedException(
                "MFA code is required."
            )

        valid = admin_mfa_service.verify_code(
            db,
            user_id=user.id,
            code=mfa_code,
            allow_recovery_codes=(
                admin_mfa_service
                .recovery_codes_enabled(
                    db,
                    user=user,
                )
            ),
        )
        if not valid:
            raise UnauthorizedException(
                "Invalid MFA code."
            )

        return False

    def login(
        self,
        db: Session,
        email: str,
        password: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
        mfa_code: str | None = None,
    ) -> dict:
        normalized_email = str(email).strip().lower()
        user = user_repository.get_by_email(
            db,
            normalized_email,
        )

        if (
            user is None
            or user.hashed_password is None
        ):
            raise UnauthorizedException(
                "Invalid credentials."
            )

        if not verify_password(
            password,
            user.hashed_password,
        ):
            self._record_failed_login(
                db,
                user=user,
            )
            raise UnauthorizedException(
                "Invalid credentials."
            )

        security = self._validate_account_access(
            db,
            user=user,
        )
        mfa_setup_required = self._validate_mfa(
            db,
            user=user,
            mfa_code=mfa_code,
        )

        security.failed_login_attempts = 0
        security.locked_until = None
        security.last_login_at = utc_now()
        security.last_login_ip = ip_address

        if (
            user.is_verified
            != security.email_verified
        ):
            user.is_verified = (
                security.email_verified
            )

        db.add(user)
        db.add(security)
        db.commit()

        access_token = create_access_token(user.id)
        refresh_token = (
            self._generate_refresh_token()
        )
        refresh_token_hash = (
            self._hash_refresh_token(
                refresh_token
            )
        )
        expires_at = (
            utc_now()
            + timedelta(
                days=(
                    settings
                    .REFRESH_TOKEN_EXPIRE_DAYS
                )
            )
        )

        db_refresh_token = RefreshToken(
            user_id=user.id,
            token_hash=refresh_token_hash,
            user_agent=user_agent,
            ip_address=ip_address,
            expires_at=expires_at,
        )
        db.add(db_refresh_token)
        db.commit()

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "mfa_setup_required": (
                mfa_setup_required
            ),
        }

    def refresh_access_token(
        self,
        db: Session,
        refresh_token: str,
    ) -> dict:
        refresh_token_hash = (
            self._hash_refresh_token(
                refresh_token
            )
        )
        db_refresh_token = (
            refresh_token_repository
            .get_by_token_hash(
                db,
                refresh_token_hash,
            )
        )

        if db_refresh_token is None:
            raise UnauthorizedException(
                "Invalid refresh token."
            )
        if db_refresh_token.is_revoked:
            raise UnauthorizedException(
                "Refresh token has been revoked."
            )
        if db_refresh_token.expires_at < utc_now():
            raise UnauthorizedException(
                "Refresh token has expired."
            )

        user = user_repository.get_by_id(
            db,
            db_refresh_token.user_id,
        )
        if user is None:
            raise UnauthorizedException(
                "Invalid user."
            )

        self._validate_account_access(
            db,
            user=user,
        )

        mfa_setup_required = bool(
            admin_mfa_service.is_required(
                db,
                user=user,
            )
            and not admin_mfa_service.is_enabled(
                db,
                user_id=user.id,
            )
        )

        access_token = create_access_token(
            user.id
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "mfa_setup_required": (
                mfa_setup_required
            ),
        }

    def logout(
        self,
        db: Session,
        refresh_token: str,
    ) -> None:
        refresh_token_hash = (
            self._hash_refresh_token(
                refresh_token
            )
        )
        db_refresh_token = (
            refresh_token_repository
            .get_by_token_hash(
                db,
                refresh_token_hash,
            )
        )
        if db_refresh_token is None:
            return

        db_refresh_token.is_revoked = True
        db_refresh_token.revoked_at = utc_now()
        db.add(db_refresh_token)
        db.commit()

    def revoke_all_user_sessions(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> int:
        sessions = (
            refresh_token_repository
            .get_active_by_user_id(
                db=db,
                user_id=user_id,
            )
        )
        revoked = 0
        now = utc_now()

        for session in sessions:
            if session.is_revoked:
                continue
            session.is_revoked = True
            session.revoked_at = now
            db.add(session)
            revoked += 1

        if revoked > 0:
            db.commit()

        return revoked

    def get_user_sessions(
        self,
        db: Session,
        user: User,
    ) -> list[RefreshToken]:
        return (
            refresh_token_repository
            .get_active_by_user_id(
                db=db,
                user_id=user.id,
            )
        )

    def admin_get_user_sessions(
        self,
        db: Session,
        user_id: int,
    ) -> list[RefreshToken]:
        return (
            refresh_token_repository
            .get_all_by_user_id(
                db=db,
                user_id=user_id,
            )
        )

    def admin_revoke_session(
        self,
        db: Session,
        session_id: int,
    ) -> None:
        session = (
            refresh_token_repository
            .get_by_id(
                db,
                session_id,
            )
        )
        if session is None:
            return

        session.is_revoked = True
        session.revoked_at = utc_now()
        db.add(session)
        db.commit()


auth_service = AuthService()
