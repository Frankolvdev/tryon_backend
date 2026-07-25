from datetime import datetime
from typing import Any

from app.common.cache_enums import CacheNamespace
from app.services.distributed_cache_service import (
    distributed_cache_service,
)


class SessionCacheService:
    DEFAULT_TTL_SECONDS = 900

    def store_session(
        self,
        *,
        session_id: str,
        user_id: int,
        expires_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
        ttl_seconds: int | None = None,
    ) -> bool:
        resolved_ttl = (
            ttl_seconds
            or self.DEFAULT_TTL_SECONDS
        )

        result = distributed_cache_service.set(
            namespace=CacheNamespace.SECURITY,
            parts=["session", session_id],
            value={
                "session_id": session_id,
                "user_id": user_id,
                "expires_at": expires_at,
                "metadata": metadata or {},
            },
            ttl_seconds=resolved_ttl,
            tags=[
                f"user:{user_id}",
                f"session:{session_id}",
                "sessions",
            ],
        )

        return result.stored

    def get_session(
        self,
        *,
        session_id: str,
    ) -> dict[str, Any] | None:
        result = distributed_cache_service.get(
            namespace=CacheNamespace.SECURITY,
            parts=["session", session_id],
        )

        if not result.found:
            return None

        if not isinstance(result.value, dict):
            return None

        return result.value

    def delete_session(
        self,
        *,
        session_id: str,
    ) -> bool:
        result = distributed_cache_service.invalidate_tag(
            tag=f"session:{session_id}"
        )

        return result.deleted_count > 0

    def delete_user_sessions(
        self,
        *,
        user_id: int,
    ) -> int:
        result = distributed_cache_service.invalidate_tag(
            tag=f"user:{user_id}"
        )

        return result.deleted_count


session_cache_service = SessionCacheService()