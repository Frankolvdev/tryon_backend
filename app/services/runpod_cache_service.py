from collections.abc import Callable
from typing import Any

from app.common.cache_enums import CacheNamespace
from app.schemas.runtime_cache import (
    RunPodStatusCacheResponse,
)
from app.services.cache_stampede_service import (
    cache_stampede_service,
)
from app.services.distributed_cache_service import (
    distributed_cache_service,
)


class RunPodCacheService:
    QUEUED_STATUS_TTL_SECONDS = 2
    RUNNING_STATUS_TTL_SECONDS = 2
    TERMINAL_STATUS_TTL_SECONDS = 300
    HEALTH_TTL_SECONDS = 10

    TERMINAL_STATUSES = {
        "COMPLETED",
        "FAILED",
        "CANCELLED",
        "TIMED_OUT",
    }

    def _status_ttl(
        self,
        status: str,
    ) -> int:
        normalized = status.upper()

        if normalized in self.TERMINAL_STATUSES:
            return self.TERMINAL_STATUS_TTL_SECONDS

        if normalized == "IN_PROGRESS":
            return self.RUNNING_STATUS_TTL_SECONDS

        return self.QUEUED_STATUS_TTL_SECONDS

    def store_status(
        self,
        *,
        provider_job_id: str,
        endpoint_id: str,
        value: dict[str, Any],
    ) -> bool:
        status = str(
            value.get(
                "status",
                "UNKNOWN",
            )
        ).upper()

        result = distributed_cache_service.set(
            namespace=CacheNamespace.RUNPOD,
            parts=[
                "status",
                endpoint_id,
                provider_job_id,
            ],
            value=value,
            ttl_seconds=self._status_ttl(
                status
            ),
            tags=[
                "runpod",
                f"runpod-endpoint:{endpoint_id}",
                f"runpod-job:{provider_job_id}",
            ],
        )

        return result.stored

    def get_status(
        self,
        *,
        provider_job_id: str,
        endpoint_id: str,
    ) -> RunPodStatusCacheResponse:
        result = distributed_cache_service.get(
            namespace=CacheNamespace.RUNPOD,
            parts=[
                "status",
                endpoint_id,
                provider_job_id,
            ],
        )

        value = (
            result.value
            if isinstance(result.value, dict)
            else None
        )

        return RunPodStatusCacheResponse(
            found=result.found,
            provider_job_id=provider_job_id,
            endpoint_id=endpoint_id,
            status=(
                str(value.get("status"))
                if value
                and value.get("status") is not None
                else None
            ),
            value=value,
            ttl_seconds=result.ttl_seconds,
        )

    def remember_status(
        self,
        *,
        provider_job_id: str,
        endpoint_id: str,
        loader: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        cached = self.get_status(
            provider_job_id=provider_job_id,
            endpoint_id=endpoint_id,
        )

        if cached.found and cached.value:
            return cached.value

        value = cache_stampede_service.remember(
            namespace=CacheNamespace.RUNPOD,
            parts=[
                "status",
                endpoint_id,
                provider_job_id,
            ],
            loader=loader,
            ttl_seconds=2,
            tags=[
                "runpod",
                f"runpod-endpoint:{endpoint_id}",
                f"runpod-job:{provider_job_id}",
            ],
            lock_ttl_seconds=10,
            lock_wait_seconds=1.0,
            poll_interval_seconds=0.05,
            jitter_ratio=0.0,
        )

        status = str(
            value.get(
                "status",
                "UNKNOWN",
            )
        )

        self.store_status(
            provider_job_id=provider_job_id,
            endpoint_id=endpoint_id,
            value=value,
        )

        if status.upper() in self.TERMINAL_STATUSES:
            self.store_status(
                provider_job_id=provider_job_id,
                endpoint_id=endpoint_id,
                value=value,
            )

        return value

    def remember_health(
        self,
        *,
        endpoint_id: str,
        loader: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        return cache_stampede_service.remember(
            namespace=CacheNamespace.RUNPOD,
            parts=[
                "health",
                endpoint_id,
            ],
            loader=loader,
            ttl_seconds=self.HEALTH_TTL_SECONDS,
            tags=[
                "runpod",
                f"runpod-endpoint:{endpoint_id}",
            ],
            lock_ttl_seconds=10,
            lock_wait_seconds=1.0,
            jitter_ratio=0.10,
        )

    def invalidate_job(
        self,
        *,
        provider_job_id: str,
    ) -> int:
        result = distributed_cache_service.invalidate_tag(
            tag=f"runpod-job:{provider_job_id}"
        )

        return result.deleted_count

    def invalidate_endpoint(
        self,
        *,
        endpoint_id: str,
    ) -> int:
        result = distributed_cache_service.invalidate_tag(
            tag=f"runpod-endpoint:{endpoint_id}"
        )

        return result.deleted_count


runpod_cache_service = RunPodCacheService()