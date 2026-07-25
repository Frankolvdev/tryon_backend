from typing import Any

from app.common.cache_enums import CacheNamespace
from app.common.time import utc_now
from app.schemas.runtime_cache import (
    JobProgressCacheResponse,
    JobProgressCacheValue,
)
from app.services.distributed_cache_service import (
    distributed_cache_service,
)


class JobProgressCacheService:
    ACTIVE_TTL_SECONDS = 3600
    TERMINAL_TTL_SECONDS = 900

    TERMINAL_STATUSES = {
        "succeeded",
        "failed",
        "canceled",
        "timed_out",
        "dead_letter",
    }

    def _ttl_for_status(
        self,
        status: str,
    ) -> int:
        if (
            status.lower()
            in self.TERMINAL_STATUSES
        ):
            return self.TERMINAL_TTL_SECONDS

        return self.ACTIVE_TTL_SECONDS

    def store(
        self,
        *,
        job_id: int,
        public_id: str,
        status: str,
        progress: float,
        message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> JobProgressCacheValue:
        value = JobProgressCacheValue(
            job_id=job_id,
            public_id=public_id,
            status=status,
            progress=min(
                max(
                    float(progress),
                    0.0,
                ),
                100.0,
            ),
            message=message,
            metadata=metadata or {},
            updated_at=utc_now(),
        )

        distributed_cache_service.set(
            namespace=CacheNamespace.TRYON,
            parts=[
                "background-job-progress",
                public_id,
            ],
            value=value.model_dump(
                mode="json"
            ),
            ttl_seconds=self._ttl_for_status(
                status
            ),
            tags=[
                "background-job-progress",
                (
                    f"background-job:"
                    f"{public_id}"
                ),
                (
                    f"background-job-id:"
                    f"{job_id}"
                ),
            ],
        )

        return value

    def get(
        self,
        *,
        public_id: str,
    ) -> JobProgressCacheResponse:
        result = distributed_cache_service.get(
            namespace=CacheNamespace.TRYON,
            parts=[
                "background-job-progress",
                public_id,
            ],
        )

        if (
            not result.found
            or not isinstance(
                result.value,
                dict,
            )
        ):
            return JobProgressCacheResponse(
                found=False,
                value=None,
                ttl_seconds=None,
            )

        return JobProgressCacheResponse(
            found=True,
            value=JobProgressCacheValue(
                **result.value
            ),
            ttl_seconds=result.ttl_seconds,
        )

    def invalidate(
        self,
        *,
        public_id: str,
    ) -> int:
        result = distributed_cache_service.invalidate_tag(
            tag=(
                f"background-job:"
                f"{public_id}"
            )
        )

        return result.deleted_count


job_progress_cache_service = (
    JobProgressCacheService()
)