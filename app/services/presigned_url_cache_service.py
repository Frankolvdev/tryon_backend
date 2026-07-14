from datetime import timedelta
from typing import Any

from app.common.cache_enums import CacheNamespace
from app.common.time import utc_now
from app.schemas.runtime_cache import (
    PresignedUrlCacheResponse,
)
from app.services.cache_stampede_service import (
    cache_stampede_service,
)
from app.services.distributed_cache_service import (
    distributed_cache_service,
)


class PresignedUrlCacheService:
    SAFETY_MARGIN_SECONDS = 60

    def _cache_ttl(
        self,
        expires_in_seconds: int,
    ) -> int:
        return max(
            expires_in_seconds
            - self.SAFETY_MARGIN_SECONDS,
            30,
        )

    def remember(
        self,
        *,
        storage_file_id: int,
        object_key: str,
        expires_in_seconds: int,
        loader,
    ) -> str:
        value = cache_stampede_service.remember(
            namespace=CacheNamespace.STORAGE,
            parts=[
                "presigned-url",
                storage_file_id,
                object_key,
                expires_in_seconds,
            ],
            loader=lambda: {
                "url": loader(),
                "storage_file_id": (
                    storage_file_id
                ),
                "object_key": object_key,
                "expires_at": (
                    utc_now()
                    + timedelta(
                        seconds=expires_in_seconds
                    )
                ),
            },
            ttl_seconds=self._cache_ttl(
                expires_in_seconds
            ),
            tags=[
                "storage",
                (
                    f"storage-file:"
                    f"{storage_file_id}"
                ),
                (
                    f"storage-object:"
                    f"{object_key}"
                ),
            ],
            lock_ttl_seconds=15,
            lock_wait_seconds=1.0,
            jitter_ratio=0.0,
        )

        return str(value["url"])

    def get(
        self,
        *,
        storage_file_id: int,
        object_key: str,
        expires_in_seconds: int,
    ) -> PresignedUrlCacheResponse:
        result = distributed_cache_service.get(
            namespace=CacheNamespace.STORAGE,
            parts=[
                "presigned-url",
                storage_file_id,
                object_key,
                expires_in_seconds,
            ],
        )

        value: dict[str, Any] | None = (
            result.value
            if isinstance(result.value, dict)
            else None
        )

        return PresignedUrlCacheResponse(
            found=result.found,
            storage_file_id=storage_file_id,
            url=(
                str(value["url"])
                if value
                and value.get("url")
                else None
            ),
            expires_at=(
                value.get("expires_at")
                if value
                else None
            ),
            ttl_seconds=result.ttl_seconds,
        )

    def invalidate_file(
        self,
        *,
        storage_file_id: int,
    ) -> int:
        result = distributed_cache_service.invalidate_tag(
            tag=(
                f"storage-file:"
                f"{storage_file_id}"
            )
        )

        return result.deleted_count

    def invalidate_object(
        self,
        *,
        object_key: str,
    ) -> int:
        result = distributed_cache_service.invalidate_tag(
            tag=(
                f"storage-object:"
                f"{object_key}"
            )
        )

        return result.deleted_count


presigned_url_cache_service = (
    PresignedUrlCacheService()
)