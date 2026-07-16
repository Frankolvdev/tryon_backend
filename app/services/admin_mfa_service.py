import base64
import hashlib
import hmac
import json
import secrets
from typing import Any, Literal

import pyotp
from cryptography.fernet import (
    Fernet,
    InvalidToken,
)
from sqlalchemy.orm import Session

from app.common.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.common.time import utc_now
from app.core.config import settings
from app.models.admin_mfa_credential import (
    AdminMfaCredential,
)
from app.models.user import User
from app.repositories.admin_mfa_repository import (
    admin_mfa_repository,
)
from app.schemas.admin_mfa import (
    AdminMfaOperationResponse,
    AdminMfaRecoveryCodesResponse,
    AdminMfaSetupResponse,
    AdminMfaStatusResponse,
)
from app.services.account_security_service import (
    account_security_service,
)

MfaAudience = Literal["admin", "user"]


class AdminMfaService:
    RECOVERY_CODE_COUNT = 10

    def _application_secret(self) -> str:
        value = getattr(settings, "SECRET_KEY", None)
        if not value:
            value = getattr(settings, "JWT_SECRET_KEY", None)
        if not value:
            raise RuntimeError(
                "SECRET_KEY or JWT_SECRET_KEY must be configured."
            )
        return str(value)

    def _fernet(self) -> Fernet:
        digest = hashlib.sha256(
            self._application_secret().encode("utf-8")
        ).digest()
        key = base64.urlsafe_b64encode(digest)
        return Fernet(key)

    def _encrypt_secret(self, secret: str) -> str:
        return (
            self._fernet()
            .encrypt(secret.encode("utf-8"))
            .decode("utf-8")
        )

    def _decrypt_secret(self, encrypted_secret: str) -> str:
        try:
            return (
                self._fernet()
                .decrypt(encrypted_secret.encode("utf-8"))
                .decode("utf-8")
            )
        except InvalidToken as error:
            raise RuntimeError(
                "The MFA secret could not be decrypted."
            ) from error

    def _hash_recovery_code(self, code: str) -> str:
        return hmac.new(
            self._application_secret().encode("utf-8"),
            code.strip().upper().encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _generate_recovery_codes(self) -> list[str]:
        return [
            f"{secrets.token_hex(3).upper()}-"
            f"{secrets.token_hex(3).upper()}"
            for _ in range(self.RECOVERY_CODE_COUNT)
        ]

    def _serialize_recovery_codes(
        self,
        codes: list[str],
    ) -> str:
        return json.dumps(
            [
                self._hash_recovery_code(code)
                for code in codes
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def _load_recovery_codes(
        self,
        credential: AdminMfaCredential,
    ) -> list[str]:
        try:
            value: Any = json.loads(
                credential.recovery_codes_json
            )
            if isinstance(value, list):
                return [str(item) for item in value]
        except (TypeError, json.JSONDecodeError):
            pass
        return []

    def _is_admin(self, user: User) -> bool:
        return bool(
            user.is_superuser
            or user.role in {
                "admin",
                "superadmin",
                "super_admin",
            }
        )

    def audience_for_user(self, user: User) -> MfaAudience:
        return "admin" if self._is_admin(user) else "user"

    def _require_audience(
        self,
        user: User,
        audience: MfaAudience,
    ) -> None:
        if audience == "admin" and not self._is_admin(user):
            raise ForbiddenException(
                "Administrator access is required."
            )
        if audience == "user" and self._is_admin(user):
            raise ForbiddenException(
                "Use the administrative MFA endpoints."
            )

    def _settings_for_audience(
        self,
        db: Session,
        *,
        audience: MfaAudience,
    ) -> tuple[bool, bool, bool]:
        config = (
            account_security_service
            .get_or_create_settings(db)
        )

        if audience == "admin":
            return (
                True,
                bool(config.admin_mfa_totp_enabled),
                bool(
                    config.admin_mfa_recovery_codes_enabled
                ),
            )

        return (
            bool(config.user_mfa_available),
            bool(config.user_mfa_totp_enabled),
            bool(
                config.user_mfa_recovery_codes_enabled
            ),
        )

    def is_available(
        self,
        db: Session,
        *,
        user: User,
    ) -> bool:
        audience = self.audience_for_user(user)
        available, _, _ = self._settings_for_audience(
            db,
            audience=audience,
        )
        return available

    def is_required(
        self,
        db: Session,
        *,
        user: User,
    ) -> bool:
        config = (
            account_security_service
            .get_or_create_settings(db)
        )
        if self._is_admin(user):
            return bool(config.admin_mfa_required)
        return bool(
            config.user_mfa_available
            and config.user_mfa_required
        )

    def totp_enabled(
        self,
        db: Session,
        *,
        user: User,
    ) -> bool:
        audience = self.audience_for_user(user)
        _, enabled, _ = self._settings_for_audience(
            db,
            audience=audience,
        )
        return enabled

    def recovery_codes_enabled(
        self,
        db: Session,
        *,
        user: User,
    ) -> bool:
        audience = self.audience_for_user(user)
        _, _, enabled = self._settings_for_audience(
            db,
            audience=audience,
        )
        return enabled

    def get_credential(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> AdminMfaCredential | None:
        return admin_mfa_repository.get_by_user_id(
            db,
            user_id=user_id,
        )

    def is_enabled(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> bool:
        credential = self.get_credential(
            db,
            user_id=user_id,
        )
        return bool(
            credential is not None
            and credential.is_enabled
        )

    def status(
        self,
        db: Session,
        *,
        user: User,
        audience: MfaAudience = "admin",
    ) -> AdminMfaStatusResponse:
        self._require_audience(user, audience)
        credential = self.get_credential(
            db,
            user_id=user.id,
        )
        recovery_count = 0
        if credential is not None:
            recovery_count = len(
                self._load_recovery_codes(credential)
            )

        return AdminMfaStatusResponse(
            user_id=user.id,
            required=self.is_required(db, user=user),
            configured=credential is not None,
            enabled=(
                credential.is_enabled
                if credential is not None
                else False
            ),
            method=(
                credential.method
                if credential is not None
                else None
            ),
            verified_at=(
                credential.verified_at
                if credential is not None
                else None
            ),
            last_used_at=(
                credential.last_used_at
                if credential is not None
                else None
            ),
            recovery_codes_remaining=recovery_count,
        )

    def setup(
        self,
        db: Session,
        *,
        user: User,
        audience: MfaAudience = "admin",
    ) -> AdminMfaSetupResponse:
        self._require_audience(user, audience)

        available, totp_allowed, recovery_allowed = (
            self._settings_for_audience(
                db,
                audience=audience,
            )
        )

        if not available or not totp_allowed:
            raise ForbiddenException(
                "TOTP MFA is disabled for this account type."
            )

        secret = pyotp.random_base32()
        recovery_codes = (
            self._generate_recovery_codes()
            if recovery_allowed
            else []
        )

        credential = self.get_credential(
            db,
            user_id=user.id,
        )
        if credential is None:
            credential = AdminMfaCredential(
                user_id=user.id,
                method="totp",
                secret_encrypted=self._encrypt_secret(
                    secret
                ),
                recovery_codes_json=(
                    self._serialize_recovery_codes(
                        recovery_codes
                    )
                ),
                is_enabled=False,
            )
        else:
            credential.method = "totp"
            credential.secret_encrypted = (
                self._encrypt_secret(secret)
            )
            credential.recovery_codes_json = (
                self._serialize_recovery_codes(
                    recovery_codes
                )
            )
            credential.is_enabled = False
            credential.verified_at = None
            credential.last_used_at = None

        db.add(credential)
        db.commit()
        db.refresh(credential)

        issuer = getattr(
            settings,
            "APP_NAME",
            "AI Virtual Try-On",
        )
        provisioning_uri = (
            pyotp.TOTP(secret).provisioning_uri(
                name=user.email,
                issuer_name=issuer,
            )
        )

        return AdminMfaSetupResponse(
            success=True,
            secret=secret,
            provisioning_uri=provisioning_uri,
            recovery_codes=recovery_codes,
            message=(
                "Scan the MFA code and confirm one "
                "generated code."
            ),
        )

    def _verify_totp(
        self,
        *,
        secret: str,
        code: str,
    ) -> bool:
        normalized = code.strip().replace(" ", "")
        if not normalized.isdigit():
            return False
        return bool(
            pyotp.TOTP(secret).verify(
                normalized,
                valid_window=1,
            )
        )

    def _consume_recovery_code(
        self,
        credential: AdminMfaCredential,
        *,
        code: str,
    ) -> bool:
        entered_hash = self._hash_recovery_code(code)
        stored_codes = self._load_recovery_codes(
            credential
        )

        matching_index = None
        for index, stored_hash in enumerate(
            stored_codes
        ):
            if hmac.compare_digest(
                entered_hash,
                stored_hash,
            ):
                matching_index = index
                break

        if matching_index is None:
            return False

        stored_codes.pop(matching_index)
        credential.recovery_codes_json = json.dumps(
            stored_codes,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return True

    def verify_code(
        self,
        db: Session,
        *,
        user_id: int,
        code: str,
        require_enabled: bool = True,
        consume_recovery_code: bool = True,
        allow_recovery_codes: bool = True,
    ) -> bool:
        credential = self.get_credential(
            db,
            user_id=user_id,
        )
        if credential is None:
            return False
        if require_enabled and not credential.is_enabled:
            return False

        secret = self._decrypt_secret(
            credential.secret_encrypted
        )
        valid = self._verify_totp(
            secret=secret,
            code=code,
        )

        if (
            not valid
            and consume_recovery_code
            and allow_recovery_codes
        ):
            valid = self._consume_recovery_code(
                credential,
                code=code,
            )

        if valid:
            credential.last_used_at = utc_now()
            db.add(credential)
            db.commit()

        return valid

    def confirm_setup(
        self,
        db: Session,
        *,
        user: User,
        code: str,
        audience: MfaAudience = "admin",
    ) -> AdminMfaOperationResponse:
        self._require_audience(user, audience)

        credential = self.get_credential(
            db,
            user_id=user.id,
        )
        if credential is None:
            raise NotFoundException(
                "MFA setup was not started."
            )

        valid = self.verify_code(
            db,
            user_id=user.id,
            code=code,
            require_enabled=False,
            consume_recovery_code=False,
        )
        if not valid:
            raise ConflictException(
                "Invalid MFA code."
            )

        credential = self.get_credential(
            db,
            user_id=user.id,
        )
        if credential is None:
            raise NotFoundException(
                "MFA credential not found."
            )

        credential.is_enabled = True
        credential.verified_at = utc_now()
        db.add(credential)
        db.commit()

        return AdminMfaOperationResponse(
            success=True,
            message="MFA was enabled successfully.",
        )

    def regenerate_recovery_codes(
        self,
        db: Session,
        *,
        user: User,
        code: str,
        audience: MfaAudience = "admin",
    ) -> AdminMfaRecoveryCodesResponse:
        self._require_audience(user, audience)

        if not self.recovery_codes_enabled(
            db,
            user=user,
        ):
            raise ForbiddenException(
                "Recovery codes are disabled "
                "for this account type."
            )

        if not self.verify_code(
            db,
            user_id=user.id,
            code=code,
            allow_recovery_codes=True,
        ):
            raise ConflictException(
                "Invalid MFA code."
            )

        credential = self.get_credential(
            db,
            user_id=user.id,
        )
        if credential is None:
            raise NotFoundException(
                "MFA credential not found."
            )

        recovery_codes = (
            self._generate_recovery_codes()
        )
        credential.recovery_codes_json = (
            self._serialize_recovery_codes(
                recovery_codes
            )
        )
        db.add(credential)
        db.commit()

        return AdminMfaRecoveryCodesResponse(
            success=True,
            recovery_codes=recovery_codes,
            message=(
                "New recovery codes were generated."
            ),
        )

    def disable(
        self,
        db: Session,
        *,
        user: User,
        code: str,
        audience: MfaAudience = "admin",
    ) -> AdminMfaOperationResponse:
        self._require_audience(user, audience)

        if not self.verify_code(
            db,
            user_id=user.id,
            code=code,
            allow_recovery_codes=(
                self.recovery_codes_enabled(
                    db,
                    user=user,
                )
            ),
        ):
            raise ConflictException(
                "Invalid MFA code."
            )

        if self.is_required(db, user=user):
            raise ConflictException(
                "MFA is required for this account type "
                "and cannot be disabled."
            )

        credential = self.get_credential(
            db,
            user_id=user.id,
        )
        if credential is None:
            raise NotFoundException(
                "MFA credential not found."
            )

        credential.is_enabled = False
        credential.verified_at = None
        db.add(credential)
        db.commit()

        return AdminMfaOperationResponse(
            success=True,
            message="MFA was disabled.",
        )


admin_mfa_service = AdminMfaService()
