import hashlib
import hmac
import json
import secrets
from datetime import datetime

from sqlalchemy.orm import Session

from app.common.enums import ApiKeyStatus
from app.common.exceptions import ForbiddenException, NotFoundException
from app.common.time import utc_now
from app.models.api_key import ApiKey
from app.models.user import User
from app.repositories.api_key_repository import api_key_repository
from app.repositories.user_repository import user_repository
from app.schemas.api_key import (
    ApiKeyCreate,
    ApiKeyCreateResponse,
    ApiKeyResponse,
    ApiKeyUpdate,
    ApiKeyValidationResponse,
)


class ApiKeyService:
    def _serialize_list(self, values: list[str]) -> str:
        return json.dumps(values or [])

    def _parse_list(self, value: str | None) -> list[str]:
        if not value:
            return []

        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
            return []
        except json.JSONDecodeError:
            return []

    def _hash_key(self, api_key: str) -> str:
        return hashlib.sha256(api_key.encode("utf-8")).hexdigest()

    def _safe_compare(self, plain_key: str, stored_hash: str) -> bool:
        return hmac.compare_digest(self._hash_key(plain_key), stored_hash)

    def _generate_api_key(self) -> tuple[str, str]:
        prefix = f"tryon_{secrets.token_urlsafe(8)}"
        secret = secrets.token_urlsafe(32)
        full_key = f"{prefix}.{secret}"
        return prefix, full_key

    def _extract_prefix(self, api_key: str) -> str | None:
        if "." not in api_key:
            return None

        return api_key.split(".", 1)[0]

    def _to_response(self, api_key: ApiKey) -> ApiKeyResponse:
        return ApiKeyResponse(
            id=api_key.id,
            name=api_key.name,
            key_prefix=api_key.key_prefix,
            api_key_type=api_key.api_key_type,
            status=api_key.status,
            user_id=api_key.user_id,
            created_by_user_id=api_key.created_by_user_id,
            scopes=self._parse_list(api_key.scopes_json),
            allowed_ips=self._parse_list(api_key.allowed_ips_json),
            description=api_key.description,
            is_active=api_key.is_active,
            last_used_at=api_key.last_used_at,
            expires_at=api_key.expires_at,
            revoked_at=api_key.revoked_at,
            created_at=api_key.created_at,
            updated_at=api_key.updated_at,
        )

    def list_api_keys(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ApiKeyResponse]:
        api_keys = api_key_repository.list_all(db, skip=skip, limit=limit)
        return [self._to_response(api_key) for api_key in api_keys]

    def list_user_api_keys(
        self,
        db: Session,
        *,
        user_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ApiKeyResponse]:
        api_keys = api_key_repository.list_by_user_id(
            db,
            user_id,
            skip=skip,
            limit=limit,
        )

        return [self._to_response(api_key) for api_key in api_keys]

    def create_api_key(
        self,
        db: Session,
        *,
        data: ApiKeyCreate,
        created_by_user: User | None = None,
    ) -> ApiKeyCreateResponse:
        if data.user_id is not None:
            user = user_repository.get_by_id(db, data.user_id)

            if not user:
                raise NotFoundException("User not found.")

        prefix, plain_key = self._generate_api_key()

        record = api_key_repository.create(
            db,
            data={
                "name": data.name,
                "key_prefix": prefix,
                "key_hash": self._hash_key(plain_key),
                "api_key_type": data.api_key_type.value,
                "status": ApiKeyStatus.ACTIVE.value,
                "user_id": data.user_id,
                "created_by_user_id": created_by_user.id if created_by_user else None,
                "scopes_json": self._serialize_list(data.scopes),
                "allowed_ips_json": self._serialize_list(data.allowed_ips),
                "description": data.description,
                "is_active": True,
                "expires_at": data.expires_at,
            },
        )

        return ApiKeyCreateResponse(
            api_key=plain_key,
            record=self._to_response(record),
        )

    def update_api_key(
        self,
        db: Session,
        *,
        api_key_id: int,
        data: ApiKeyUpdate,
    ) -> ApiKeyResponse:
        api_key = api_key_repository.get_by_id(db, api_key_id)

        if not api_key:
            raise NotFoundException("API key not found.")

        update_data = data.model_dump(exclude_unset=True)

        final_data = {}

        for field in ["name", "description", "expires_at", "is_active"]:
            if field in update_data:
                final_data[field] = update_data[field]

        if "scopes" in update_data:
            final_data["scopes_json"] = self._serialize_list(update_data["scopes"])

        if "allowed_ips" in update_data:
            final_data["allowed_ips_json"] = self._serialize_list(update_data["allowed_ips"])

        updated = api_key_repository.update(
            db,
            db_obj=api_key,
            data=final_data,
        )

        return self._to_response(updated)

    def revoke_api_key(
        self,
        db: Session,
        *,
        api_key_id: int,
    ) -> None:
        api_key = api_key_repository.get_by_id(db, api_key_id)

        if not api_key:
            raise NotFoundException("API key not found.")

        api_key.status = ApiKeyStatus.REVOKED.value
        api_key.is_active = False
        api_key.revoked_at = utc_now()

        db.add(api_key)
        db.commit()

    def validate_api_key(
        self,
        db: Session,
        *,
        plain_key: str,
        required_scope: str | None = None,
        ip_address: str | None = None,
    ) -> ApiKeyValidationResponse:
        prefix = self._extract_prefix(plain_key)

        if not prefix:
            return ApiKeyValidationResponse(valid=False)

        api_key = api_key_repository.get_by_prefix(db, prefix)

        if not api_key:
            return ApiKeyValidationResponse(valid=False)

        if not api_key.is_active or api_key.status != ApiKeyStatus.ACTIVE.value:
            return ApiKeyValidationResponse(valid=False)

        if api_key.expires_at and api_key.expires_at < utc_now():
            api_key.status = ApiKeyStatus.EXPIRED.value
            api_key.is_active = False
            db.add(api_key)
            db.commit()
            return ApiKeyValidationResponse(valid=False)

        if not self._safe_compare(plain_key, api_key.key_hash):
            return ApiKeyValidationResponse(valid=False)

        scopes = self._parse_list(api_key.scopes_json)
        allowed_ips = self._parse_list(api_key.allowed_ips_json)

        if required_scope and required_scope not in scopes and "*" not in scopes:
            return ApiKeyValidationResponse(valid=False)

        if allowed_ips and ip_address and ip_address not in allowed_ips:
            return ApiKeyValidationResponse(valid=False)

        api_key.last_used_at = utc_now()
        db.add(api_key)
        db.commit()

        return ApiKeyValidationResponse(
            valid=True,
            api_key_id=api_key.id,
            user_id=api_key.user_id,
            scopes=scopes,
            metadata={
                "key_prefix": api_key.key_prefix,
                "api_key_type": api_key.api_key_type,
            },
        )

    def require_valid_api_key(
        self,
        db: Session,
        *,
        plain_key: str,
        required_scope: str | None = None,
        ip_address: str | None = None,
    ) -> ApiKeyValidationResponse:
        result = self.validate_api_key(
            db,
            plain_key=plain_key,
            required_scope=required_scope,
            ip_address=ip_address,
        )

        if not result.valid:
            raise ForbiddenException("Invalid or unauthorized API key.")

        return result


api_key_service = ApiKeyService()