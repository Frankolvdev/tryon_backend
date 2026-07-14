from typing import Any

from app.common.cache_enums import CacheNamespace
from app.schemas.runtime_cache import (
    TryOnRuntimeCacheResponse,
)
from app.services.cache_stampede_service import (
    cache_stampede_service,
)
from app.services.distributed_cache_service import (
    distributed_cache_service,
)


class TryOnCacheService:
    JOB_TTL_SECONDS = 300
    INPUT_TTL_SECONDS = 600
    PREPARED_WORKFLOW_TTL_SECONDS = 300
    RESULT_TTL_SECONDS = 900

    def remember_job(
        self,
        *,
        tryon_job_id: int,
        loader,
    ) -> Any:
        return cache_stampede_service.remember_optional(
            namespace=CacheNamespace.TRYON,
            parts=[
                "job",
                tryon_job_id,
            ],
            loader=loader,
            ttl_seconds=self.JOB_TTL_SECONDS,
            negative_ttl_seconds=20,
            tags=[
                "tryon",
                f"tryon-job:{tryon_job_id}",
            ],
            lock_ttl_seconds=20,
            lock_wait_seconds=1.5,
            jitter_ratio=0.10,
        )

    def store_inputs(
        self,
        *,
        tryon_job_id: int,
        value: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> bool:
        result = distributed_cache_service.set(
            namespace=CacheNamespace.TRYON,
            parts=[
                "inputs",
                tryon_job_id,
            ],
            value=value,
            ttl_seconds=(
                ttl_seconds
                or self.INPUT_TTL_SECONDS
            ),
            tags=[
                "tryon",
                f"tryon-job:{tryon_job_id}",
                f"tryon-inputs:{tryon_job_id}",
            ],
        )

        return result.stored

    def get_inputs(
        self,
        *,
        tryon_job_id: int,
    ) -> TryOnRuntimeCacheResponse:
        result = distributed_cache_service.get(
            namespace=CacheNamespace.TRYON,
            parts=[
                "inputs",
                tryon_job_id,
            ],
        )

        return TryOnRuntimeCacheResponse(
            found=result.found,
            tryon_job_id=tryon_job_id,
            value=(
                result.value
                if isinstance(result.value, dict)
                else None
            ),
            ttl_seconds=result.ttl_seconds,
        )

    def store_prepared_workflow(
        self,
        *,
        tryon_job_id: int,
        workflow_id: int | None,
        execution_mode: str,
        workflow: dict[str, Any],
        variables: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> bool:
        result = distributed_cache_service.set(
            namespace=CacheNamespace.TRYON,
            parts=[
                "prepared-workflow",
                tryon_job_id,
                workflow_id or "default",
                execution_mode,
            ],
            value={
                "tryon_job_id": tryon_job_id,
                "workflow_id": workflow_id,
                "execution_mode": execution_mode,
                "workflow": workflow,
                "variables": variables,
            },
            ttl_seconds=(
                ttl_seconds
                or self.PREPARED_WORKFLOW_TTL_SECONDS
            ),
            tags=[
                "tryon",
                f"tryon-job:{tryon_job_id}",
                f"tryon-workflow:{tryon_job_id}",
                "workflows",
            ],
        )

        return result.stored

    def get_prepared_workflow(
        self,
        *,
        tryon_job_id: int,
        workflow_id: int | None,
        execution_mode: str,
    ) -> dict[str, Any] | None:
        result = distributed_cache_service.get(
            namespace=CacheNamespace.TRYON,
            parts=[
                "prepared-workflow",
                tryon_job_id,
                workflow_id or "default",
                execution_mode,
            ],
        )

        if not result.found:
            return None

        if not isinstance(result.value, dict):
            return None

        return result.value

    def store_result(
        self,
        *,
        tryon_job_id: int,
        value: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> bool:
        result = distributed_cache_service.set(
            namespace=CacheNamespace.TRYON,
            parts=[
                "result",
                tryon_job_id,
            ],
            value=value,
            ttl_seconds=(
                ttl_seconds
                or self.RESULT_TTL_SECONDS
            ),
            tags=[
                "tryon",
                f"tryon-job:{tryon_job_id}",
                f"tryon-result:{tryon_job_id}",
            ],
        )

        return result.stored

    def get_result(
        self,
        *,
        tryon_job_id: int,
    ) -> TryOnRuntimeCacheResponse:
        result = distributed_cache_service.get(
            namespace=CacheNamespace.TRYON,
            parts=[
                "result",
                tryon_job_id,
            ],
        )

        return TryOnRuntimeCacheResponse(
            found=result.found,
            tryon_job_id=tryon_job_id,
            value=(
                result.value
                if isinstance(result.value, dict)
                else None
            ),
            ttl_seconds=result.ttl_seconds,
        )

    def invalidate_job(
        self,
        *,
        tryon_job_id: int,
    ) -> int:
        result = distributed_cache_service.invalidate_tag(
            tag=f"tryon-job:{tryon_job_id}"
        )

        return result.deleted_count

    def invalidate_all(
        self,
    ) -> int:
        result = (
            distributed_cache_service
            .invalidate_namespace(
                namespace=CacheNamespace.TRYON
            )
        )

        return result.deleted_count


tryon_cache_service = TryOnCacheService()