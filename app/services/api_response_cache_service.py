from collections.abc import Callable
from typing import Any, TypeVar

from app.common.cache_enums import CacheNamespace
from app.services.cache_stampede_service import (
    cache_stampede_service,
)
from app.services.distributed_cache_service import (
    distributed_cache_service,
)


T = TypeVar("T")


class ApiResponseCacheService:
    DEFAULT_TTL_SECONDS = 60

    def remember(
        self,
        *,
        endpoint_name: str,
        query_params: dict[str, Any],
        loader: Callable[[], T],
        ttl_seconds: int | None = None,
        tags: list[str] | None = None,
        user_id: int | None = None,
    ) -> T:
        parts: list[Any] = [
            endpoint_name,
            query_params,
        ]

        resolved_tags = list(
            tags or []
        )

        if user_id is not None:
            parts.append(
                {
                    "user_id": user_id,
                }
            )

            resolved_tags.append(
                f"user:{user_id}"
            )

        return cache_stampede_service.remember(
            namespace=CacheNamespace.API,
            parts=parts,
            loader=loader,
            ttl_seconds=(
                ttl_seconds
                or self.DEFAULT_TTL_SECONDS
            ),
            tags=[
                "api-responses",
                f"api-endpoint:{endpoint_name}",
                *resolved_tags,
            ],
            lock_ttl_seconds=15,
            lock_wait_seconds=1.5,
            jitter_ratio=0.15,
        )

    def invalidate_endpoint(
        self,
        *,
        endpoint_name: str,
    ) -> None:
        distributed_cache_service.invalidate_tag(
            tag=f"api-endpoint:{endpoint_name}"
        )

    def invalidate_all(
        self,
    ) -> None:
        distributed_cache_service.invalidate_tag(
            tag="api-responses"
        )

        distributed_cache_service.invalidate_namespace(
            namespace=CacheNamespace.API
        )


api_response_cache_service = (
    ApiResponseCacheService()
)