import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from app.common.exceptions import (
    ConflictException,
    NotFoundException,
)
from app.common.rate_limit_enums import (
    BlockTargetType,
)
from app.common.time import utc_now
from app.models.security_block import SecurityBlock
from app.repositories.security_block_repository import (
    security_block_repository,
)
from app.schemas.rate_limit import (
    SecurityBlockCreate,
    SecurityBlockListResponse,
    SecurityBlockResponse,
)
from app.schemas.rate_limit_runtime import (
    RateLimitIdentity,
)


class SecurityBlockService:
    def _serialize_json(self, value: Any) -> str:
        return json.dumps(
            value or {},
            ensure_ascii=False,
            default=str,
        )

    def _parse_json(
        self,
        value: str | None,
    ) -> dict[str, Any]:
        if not value:
            return {}

        try:
            parsed = json.loads(value)

            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _normalize_target(
        self,
        target_type: str,
        target_value: str,
    ) -> str:
        value = target_value.strip()

        if target_type == BlockTargetType.EMAIL.value:
            return value.lower()

        return value

    def _to_response(
        self,
        block: SecurityBlock,
    ) -> SecurityBlockResponse:
        return SecurityBlockResponse(
            id=block.id,
            target_type=block.target_type,
            target_value=block.target_value,
            reason=block.reason,
            abuse_event_id=block.abuse_event_id,
            created_by_user_id=(
                block.created_by_user_id
            ),
            starts_at=block.starts_at,
            expires_at=block.expires_at,
            is_permanent=block.is_permanent,
            is_active=block.is_active,
            metadata=self._parse_json(
                block.metadata_json
            ),
            created_at=block.created_at,
            updated_at=block.updated_at,
        )

    def get_block(
        self,
        db: Session,
        *,
        block_id: int,
    ) -> SecurityBlock:
        block = security_block_repository.get_by_id(
            db,
            block_id,
        )

        if not block:
            raise NotFoundException(
                "Security block not found."
            )

        return block

    def get_response(
        self,
        db: Session,
        *,
        block_id: int,
    ) -> SecurityBlockResponse:
        return self._to_response(
            self.get_block(
                db,
                block_id=block_id,
            )
        )

    def list_blocks(
        self,
        db: Session,
        *,
        target_type: BlockTargetType | None = None,
        is_active: bool | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> SecurityBlockListResponse:
        blocks = security_block_repository.list_filtered(
            db,
            target_type=(
                target_type.value
                if target_type
                else None
            ),
            is_active=is_active,
            skip=skip,
            limit=limit,
        )

        total = security_block_repository.count_filtered(
            db,
            target_type=(
                target_type.value
                if target_type
                else None
            ),
            is_active=is_active,
        )

        return SecurityBlockListResponse(
            items=[
                self._to_response(block)
                for block in blocks
            ],
            total=total,
            skip=skip,
            limit=limit,
        )

    def create_block(
        self,
        db: Session,
        *,
        data: SecurityBlockCreate,
        created_by_user_id: int | None,
    ) -> SecurityBlockResponse:
        target_value = self._normalize_target(
            data.target_type.value,
            data.target_value,
        )

        existing = (
            security_block_repository.find_active_block(
                db,
                target_type=data.target_type.value,
                target_value=target_value,
            )
        )

        if existing:
            raise ConflictException(
                "An active block already exists for this target."
            )

        if (
            not data.is_permanent
            and data.expires_at is None
        ):
            raise ConflictException(
                "expires_at is required for a temporary block."
            )

        if (
            data.expires_at is not None
            and data.expires_at <= utc_now()
        ):
            raise ConflictException(
                "Block expiration must be in the future."
            )

        block = SecurityBlock(
            target_type=data.target_type.value,
            target_value=target_value,
            reason=data.reason,
            abuse_event_id=data.abuse_event_id,
            created_by_user_id=created_by_user_id,
            starts_at=utc_now(),
            expires_at=(
                None
                if data.is_permanent
                else data.expires_at
            ),
            is_permanent=data.is_permanent,
            is_active=True,
            metadata_json=self._serialize_json(
                data.metadata
            ),
        )

        db.add(block)
        db.commit()
        db.refresh(block)

        return self._to_response(block)

    def deactivate_block(
        self,
        db: Session,
        *,
        block_id: int,
    ) -> SecurityBlockResponse:
        block = self.get_block(
            db,
            block_id=block_id,
        )

        block.is_active = False

        db.add(block)
        db.commit()
        db.refresh(block)

        return self._to_response(block)

    def reactivate_block(
        self,
        db: Session,
        *,
        block_id: int,
    ) -> SecurityBlockResponse:
        block = self.get_block(
            db,
            block_id=block_id,
        )

        if (
            not block.is_permanent
            and block.expires_at is not None
            and block.expires_at <= utc_now()
        ):
            raise ConflictException(
                "An expired block cannot be reactivated."
            )

        active_duplicate = (
            security_block_repository.find_active_block(
                db,
                target_type=block.target_type,
                target_value=block.target_value,
            )
        )

        if (
            active_duplicate
            and active_duplicate.id != block.id
        ):
            raise ConflictException(
                "Another active block already exists for this target."
            )

        block.is_active = True

        db.add(block)
        db.commit()
        db.refresh(block)

        return self._to_response(block)

    def _api_key_target(
        self,
        identity: RateLimitIdentity,
    ) -> str | None:
        if identity.api_key_id is not None:
            return str(identity.api_key_id)

        if identity.api_key_hash:
            return identity.api_key_hash

        return None

    def find_identity_block(
        self,
        db: Session,
        *,
        identity: RateLimitIdentity,
    ) -> SecurityBlock | None:
        candidates: list[tuple[str, str]] = []

        if identity.ip_address:
            candidates.append(
                (
                    BlockTargetType.IP.value,
                    identity.ip_address,
                )
            )

        if identity.user_id is not None:
            candidates.append(
                (
                    BlockTargetType.USER.value,
                    str(identity.user_id),
                )
            )

        api_key_target = self._api_key_target(
            identity
        )

        if api_key_target:
            candidates.append(
                (
                    BlockTargetType.API_KEY.value,
                    api_key_target,
                )
            )

        for target_type, target_value in candidates:
            block = (
                security_block_repository.find_active_block(
                    db,
                    target_type=target_type,
                    target_value=target_value,
                )
            )

            if block:
                return block

        return None

    def block_from_rate_limit_event(
        self,
        db: Session,
        *,
        abuse_event_id: int,
        identity: RateLimitIdentity,
        reason: str,
        expires_at,
    ) -> SecurityBlockResponse | None:
        if identity.user_id is not None:
            target_type = BlockTargetType.USER
            target_value = str(identity.user_id)
        elif identity.ip_address:
            target_type = BlockTargetType.IP
            target_value = identity.ip_address
        else:
            return None

        existing = (
            security_block_repository.find_active_block(
                db,
                target_type=target_type.value,
                target_value=target_value,
            )
        )

        if existing:
            return self._to_response(existing)

        return self.create_block(
            db,
            data=SecurityBlockCreate(
                target_type=target_type,
                target_value=target_value,
                reason=reason,
                abuse_event_id=abuse_event_id,
                expires_at=expires_at,
                is_permanent=False,
                metadata={
                    "source": "automatic_rate_limit",
                },
            ),
            created_by_user_id=None,
        )


security_block_service = SecurityBlockService()