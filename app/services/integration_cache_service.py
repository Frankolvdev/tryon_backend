from collections.abc import Callable
from typing import Any

from app.common.cache_enums import CacheNamespace
from app.services.cache_stampede_service import (
    cache_stampede_service,
)
from app.services.distributed_cache_service import (
    distributed_cache_service,
)


class IntegrationCacheService:
    CONFIG_TTL_SECONDS = 300
    HEALTH_TTL_SECONDS = 20

    def remember_config(
        self,
        *,
        provider: str,
        loader: Callable[[], dict[str, Any] | None],
    ) -> dict[str, Any] | None:
        normalized_provider = (
            provider.strip().lower()
        )

        return cache_stampede_service.remember_optional(
            namespace=CacheNamespace.INTEGRATIONS,
            parts=[
                "config",
                normalized_provider,
            ],
            loader=loader,
            ttl_seconds=self.CONFIG_TTL_SECONDS,
            negative_ttl_seconds=30,
            tags=[
                "integrations",
                (
                    f"integration:"
                    f"{normalized_provider}"
                ),
            ],
            lock_ttl_seconds=20,
            lock_wait_seconds=1.5,
        )

    def remember_health(
        self,
        *,
        provider: str,
        loader: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        normalized_provider = (
            provider.strip().lower()
        )

        return cache_stampede_service.remember(
            namespace=CacheNamespace.INTEGRATIONS,
            parts=[
                "health",
                normalized_provider,
            ],
            loader=loader,
            ttl_seconds=self.HEALTH_TTL_SECONDS,
            tags=[
                "integrations",
                (
                    f"integration:"
                    f"{normalized_provider}"
                ),
                (
                    f"integration-health:"
                    f"{normalized_provider}"
                ),
            ],
            lock_ttl_seconds=10,
            lock_wait_seconds=1.0,
            jitter_ratio=0.10,
        )

    def invalidate_provider(
        self,
        *,
        provider: str,
    ) -> int:
        normalized_provider = (
            provider.strip().lower()
        )

        result = distributed_cache_service.invalidate_tag(
            tag=(
                f"integration:"
                f"{normalized_provider}"
            )
        )

        return result.deleted_count

    def invalidate_health(
        self,
        *,
        provider: str,
    ) -> int:
        normalized_provider = (
            provider.strip().lower()
        )

        result = distributed_cache_service.invalidate_tag(
            tag=(
                f"integration-health:"
                f"{normalized_provider}"
            )
        )

        return result.deleted_count


integration_cache_service = (
    IntegrationCacheService()
)