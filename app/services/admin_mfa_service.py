import base64
import hashlib
import hmac
import json
import secrets
from typing import Any

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


class AdminMfaService:
    RECOVERY_CODE_COUNT = 10

    def _application_secret(
        self,
    ) -> str:
        value = getattr(
            settings,
            "SECRET_KEY",
            None,
        )

        if not value:
            value = getattr(
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

    def _fernet(
        self,
    ) -> Fernet:
        digest = hashlib.sha256(
            self._application_secret().encode(
                "utf-8"
            )
        ).digest()

        key = base64.urlsafe_b64encode(
            digest
        )

        return Fernet(key)

    def _encrypt_secret(
        self,
        secret: str,
    ) -> str:
        return (
            self._fernet()
            .encrypt(
                secret.encode("utf-8")
            )
            .decode("utf-8")
        )

    def _decrypt_secret(
        self,
        encrypted_secret: str,
    ) -> str:
        try:
            return (
                self._fernet()
                .decrypt(
                    encrypted_secret.encode(
                        "utf-8"
                    )
                )
                .decode("utf-8")
            )

        except InvalidToken as error:
            raise RuntimeError(
                "The MFA secret could not "
                "be decrypted."
            ) from error

    def _hash_recovery_code(
        self,
        code: str,
    ) -> str:
        return hmac.new(
            self._application_secret().encode(
                "utf-8"
            ),
            code.strip()
            .upper()
            .encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _generate_recovery_codes(
        self,
    ) -> list[str]:
        codes: list[str] = []

        for _ in range(
            self.RECOVERY_CODE_COUNT
        ):
            first = secrets.token_hex(
                3
            ).upper()

            second = secrets.token_hex(
                3
            ).upper()

            codes.append(
                f"{first}-{second}"
            )

        return codes

    def _serialize_recovery_codes(
        self,
        codes: list[str],
    ) -> str:
        hashed_codes = [
            self._hash_recovery_code(
                code
            )
            for code in codes
        ]

        return json.dumps(
            hashed_codes,
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def _load_recovery_codes(
        self,
        credential: AdminMfaCredential,
    ) -> list[str]:
        try:
            value: Any = json.loads(
                credential
                .recovery_codes_json
            )

            if isinstance(value, list):
                return [
                    str(item)
                    for item in value
                ]

        except (
            TypeError,
            json.JSONDecodeError,
        ):
            pass

        return []

    def _is_admin(
        self,
        user: User,
    ) -> bool:
        return bool(
            user.is_superuser
            or user.role
            in {
                "admin",
                "superadmin",
                "super_admin",
            }
        )

    def _require_admin(
        self,
        user: User,
    ) -> None:
        if not self._is_admin(user):
            raise ForbiddenException(
                "Administrator access "
                "is required."
            )

    def is_required(
        self,
        db: Session,
        *,
        user: User,
    ) -> bool:
        if not self._is_admin(user):
            return False

        config = (
            account_security_service
            .get_or_create_settings(db)
        )

        return bool(
            config.admin_mfa_required
        )

    def get_credential(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> AdminMfaCredential | None:
        return (
            admin_mfa_repository
            .get_by_user_id(
                db,
                user_id=user_id,
            )
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
    ) -> AdminMfaStatusResponse:
        self._require_admin(user)

        credential = self.get_credential(
            db,
            user_id=user.id,
        )

        recovery_count = 0

        if credential is not None:
            recovery_count = len(
                self._load_recovery_codes(
                    credential
                )
            )

        return AdminMfaStatusResponse(
            user_id=user.id,
            required=self.is_required(
                db,
                user=user,
            ),
            configured=(
                credential is not None
            ),
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
            recovery_codes_remaining=(
                recovery_count
            ),
        )

    def setup(
        self,
        db: Session,
        *,
        user: User,
    ) -> AdminMfaSetupResponse:
        self._require_admin(user)

        secret = pyotp.random_base32()

        recovery_codes = (
            self._generate_recovery_codes()
        )

        credential = self.get_credential(
            db,
            user_id=user.id,
        )

        if credential is None:
            credential = (
                AdminMfaCredential(
                    user_id=user.id,
                    method="totp",
                    secret_encrypted=(
                        self._encrypt_secret(
                            secret
                        )
                    ),
                    recovery_codes_json=(
                        self
                        ._serialize_recovery_codes(
                            recovery_codes
                        )
                    ),
                    is_enabled=False,
                )
            )

        else:
            credential.method = "totp"

            credential.secret_encrypted = (
                self._encrypt_secret(
                    secret
                )
            )

            credential.recovery_codes_json = (
                self
                ._serialize_recovery_codes(
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
            pyotp.TOTP(secret)
            .provisioning_uri(
                name=user.email,
                issuer_name=issuer,
            )
        )

        return AdminMfaSetupResponse(
            success=True,
            secret=secret,
            provisioning_uri=(
                provisioning_uri
            ),
            recovery_codes=(
                recovery_codes
            ),
            message=(
                "Scan the MFA code and "
                "confirm one generated code."
            ),
        )

    def _verify_totp(
        self,
        *,
        secret: str,
        code: str,
    ) -> bool:
        normalized = (
            code.strip()
            .replace(" ", "")
        )

        if not normalized.isdigit():
            return False

        return bool(
            pyotp.TOTP(
                secret
            ).verify(
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
        entered_hash = (
            self._hash_recovery_code(
                code
            )
        )

        stored_codes = (
            self._load_recovery_codes(
                credential
            )
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

        stored_codes.pop(
            matching_index
        )

        credential.recovery_codes_json = (
            json.dumps(
                stored_codes,
                ensure_ascii=False,
                separators=(",", ":"),
            )
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
    ) -> bool:
        credential = self.get_credential(
            db,
            user_id=user_id,
        )

        if credential is None:
            return False

        if (
            require_enabled
            and not credential.is_enabled
        ):
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
        ):
            valid = (
                self._consume_recovery_code(
                    credential,
                    code=code,
                )
            )

        if valid:
            credential.last_used_at = (
                utc_now()
            )

            db.add(credential)
            db.commit()

        return valid

    def confirm_setup(
        self,
        db: Session,
        *,
        user: User,
        code: str,
    ) -> AdminMfaOperationResponse:
        self._require_admin(user)

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
            message=(
                "Administrative MFA "
                "was enabled successfully."
            ),
        )

    def regenerate_recovery_codes(
        self,
        db: Session,
        *,
        user: User,
        code: str,
    ) -> AdminMfaRecoveryCodesResponse:
        self._require_admin(user)

        if not self.verify_code(
            db,
            user_id=user.id,
            code=code,
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

        return (
            AdminMfaRecoveryCodesResponse(
                success=True,
                recovery_codes=(
                    recovery_codes
                ),
                message=(
                    "New recovery codes "
                    "were generated."
                ),
            )
        )

    def disable(
        self,
        db: Session,
        *,
        user: User,
        code: str,
    ) -> AdminMfaOperationResponse:
        self._require_admin(user)

        if not self.verify_code(
            db,
            user_id=user.id,
            code=code,
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

        credential.is_enabled = False
        credential.verified_at = None

        db.add(credential)
        db.commit()

        return AdminMfaOperationResponse(
            success=True,
            message=(
                "Administrative MFA "
                "was disabled."
            ),
        )


admin_mfa_service = AdminMfaService()