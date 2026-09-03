from typing import Any

from app.services.job_progress_cache_service import (
    job_progress_cache_service,
)
from app.services.realtime_event_service import (
    realtime_event_service,
)


class BackgroundJobRuntimeCacheService:
    def publish_progress(
        self,
        *,
        job_id: int,
        public_id: str,
        status: str,
        progress: float,
        message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        value = job_progress_cache_service.store(
            job_id=job_id,
            public_id=public_id,
            status=status,
            progress=progress,
            message=message,
            metadata=metadata,
        )

        realtime_event_service.publish_job_progress(
            public_id=public_id,
            job_id=job_id,
            status=status,
            progress=value.progress,
            message=message,
            metadata=metadata,
        )

    def publish_terminal_result(
        self,
        *,
        job_id: int,
        public_id: str,
        status: str,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        metadata = {
            "result": result or {},
            "error": error or {},
        }

        progress = (
            100.0
            if status == "succeeded"
            else 0.0
        )

        self.publish_progress(
            job_id=job_id,
            public_id=public_id,
            status=status,
            progress=progress,
            message=(
                "Job completed successfully."
                if status == "succeeded"
                else "Job reached a terminal state."
            ),
            metadata=metadata,
        )


background_job_runtime_cache_service = (
    BackgroundJobRuntimeCacheService()
)