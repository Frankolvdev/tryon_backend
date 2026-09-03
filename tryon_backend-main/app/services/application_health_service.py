import os
import shutil
import time
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.common.time import utc_now
from app.core.config import settings
from app.core.redis_client import redis_client
from app.observability.metrics import (
    APPLICATION_LIVE,
    APPLICATION_READY,
    COMFYUI_LOCAL_AVAILABLE,
    COMFYUI_LOCAL_CONFIGURED,
    COMFYUI_LOCAL_HEALTH_CHECK_DURATION_SECONDS,
    DEPENDENCY_HEALTH,
    LOCAL_STORAGE_AVAILABLE,
    LOCAL_STORAGE_FREE_BYTES,
    LOCAL_STORAGE_TOTAL_BYTES,
    POSTGRES_AVAILABLE,
    REDIS_AVAILABLE,
    RUNPOD_AVAILABLE,
    RUNPOD_CONFIGURED,
    RUNPOD_HEALTH_CHECK_DURATION_SECONDS,
)
from app.schemas.health import (
    DependencyHealthResponse,
    LivenessResponse,
    ReadinessResponse,
    SystemHealthResponse,
)
from app.services.comfyui_local_adapter_service import (
    comfyui_local_adapter_service,
)
from app.services.runpod_runtime_config_service import (
    runpod_runtime_config_service,
)
from app.services.runpod_serverless_adapter_service import (
    runpod_serverless_adapter_service,
)


class ApplicationHealthService:
    def __init__(self):
        self.started_at = time.monotonic()

    def _setting(
        self,
        name: str,
        default: Any,
    ) -> Any:
        return getattr(
            settings,
            name,
            default,
        )

    def liveness(
        self,
    ) -> LivenessResponse:
        APPLICATION_LIVE.set(1)

        return LivenessResponse(
            status="alive",
            service=str(
                self._setting(
                    "APP_NAME",
                    "tryon-backend",
                )
            ),
            version=str(
                self._setting(
                    "APP_VERSION",
                    "1.0.0",
                )
            ),
            environment=str(
                self._setting(
                    "ENVIRONMENT",
                    "development",
                )
            ),
            process_id=os.getpid(),
            uptime_seconds=round(
                time.monotonic()
                - self.started_at,
                3,
            ),
            checked_at=utc_now(),
        )

    def _postgres_health(
        self,
        db: Session,
    ) -> DependencyHealthResponse:
        started_at = time.perf_counter()

        try:
            db.execute(
                text("SELECT 1")
            )

            latency_ms = round(
                (
                    time.perf_counter()
                    - started_at
                )
                * 1000,
                3,
            )

            POSTGRES_AVAILABLE.set(1)

            return DependencyHealthResponse(
                name="postgresql",
                status="healthy",
                required=True,
                latency_ms=latency_ms,
                message=(
                    "PostgreSQL connection is available."
                ),
            )

        except SQLAlchemyError as error:
            POSTGRES_AVAILABLE.set(0)

            return DependencyHealthResponse(
                name="postgresql",
                status="unavailable",
                required=True,
                latency_ms=None,
                message=str(error),
            )

    def _redis_health(
        self,
    ) -> DependencyHealthResponse:
        started_at = time.perf_counter()

        try:
            available = bool(
                redis_client.ping()
            )

            latency_ms = round(
                (
                    time.perf_counter()
                    - started_at
                )
                * 1000,
                3,
            )

            REDIS_AVAILABLE.set(
                1 if available else 0
            )

            return DependencyHealthResponse(
                name="redis",
                status=(
                    "healthy"
                    if available
                    else "unavailable"
                ),
                required=True,
                latency_ms=latency_ms,
                message=(
                    "Redis connection is available."
                    if available
                    else "Redis ping failed."
                ),
            )

        except Exception as error:
            REDIS_AVAILABLE.set(0)

            return DependencyHealthResponse(
                name="redis",
                status="unavailable",
                required=True,
                message=str(error),
            )

    def _storage_health(
        self,
    ) -> DependencyHealthResponse:
        storage_directory = Path(
            str(
                self._setting(
                    "LOCAL_STORAGE_DIR",
                    "storage",
                )
            )
        )

        try:
            storage_directory.mkdir(
                parents=True,
                exist_ok=True,
            )

            test_file = (
                storage_directory
                / ".health-check"
            )

            test_file.write_text(
                "ok",
                encoding="utf-8",
            )

            test_file.unlink(
                missing_ok=True
            )

            usage = shutil.disk_usage(
                storage_directory
            )

            LOCAL_STORAGE_AVAILABLE.set(1)
            LOCAL_STORAGE_TOTAL_BYTES.set(
                usage.total
            )
            LOCAL_STORAGE_FREE_BYTES.set(
                usage.free
            )

            return DependencyHealthResponse(
                name="local_storage",
                status="healthy",
                required=True,
                message=(
                    "Local storage is writable."
                ),
                details={
                    "path": str(
                        storage_directory
                    ),
                    "total_bytes": usage.total,
                    "free_bytes": usage.free,
                    "used_bytes": usage.used,
                },
            )

        except Exception as error:
            LOCAL_STORAGE_AVAILABLE.set(0)

            return DependencyHealthResponse(
                name="local_storage",
                status="unavailable",
                required=True,
                message=str(error),
                details={
                    "path": str(
                        storage_directory
                    ),
                },
            )

    def _comfyui_health(
        self,
    ) -> DependencyHealthResponse:
        configured_url = str(
            self._setting(
                "COMFYUI_BASE_URL",
                "http://127.0.0.1:8188",
            )
        )

        COMFYUI_LOCAL_CONFIGURED.set(
            1 if configured_url else 0
        )

        started_at = time.perf_counter()

        try:
            result = (
                comfyui_local_adapter_service
                .health()
            )

            duration = (
                time.perf_counter()
                - started_at
            )

            COMFYUI_LOCAL_HEALTH_CHECK_DURATION_SECONDS.observe(
                duration
            )

            available = bool(
                result.get("available")
            )

            COMFYUI_LOCAL_AVAILABLE.set(
                1 if available else 0
            )

            return DependencyHealthResponse(
                name="comfyui_local",
                status=(
                    "healthy"
                    if available
                    else "unavailable"
                ),
                required=False,
                latency_ms=round(
                    duration * 1000,
                    3,
                ),
                message=(
                    "Local ComfyUI is available."
                    if available
                    else str(
                        result.get(
                            "error",
                            "Local ComfyUI is unavailable.",
                        )
                    )
                ),
                details={
                    "base_url": result.get(
                        "base_url"
                    ),
                },
            )

        except Exception as error:
            duration = (
                time.perf_counter()
                - started_at
            )

            COMFYUI_LOCAL_HEALTH_CHECK_DURATION_SECONDS.observe(
                duration
            )

            COMFYUI_LOCAL_AVAILABLE.set(0)

            return DependencyHealthResponse(
                name="comfyui_local",
                status="unavailable",
                required=False,
                latency_ms=round(
                    duration * 1000,
                    3,
                ),
                message=str(error),
                details={
                    "base_url": configured_url,
                },
            )

    def _runpod_health(
        self,
        db: Session,
        *,
        perform_remote_check: bool,
    ) -> DependencyHealthResponse:
        api_key = (
            runpod_runtime_config_service
            .api_key(db)
        )

        endpoint_id = (
            runpod_runtime_config_service
            .endpoint_id(db)
        )

        configured = bool(
            api_key
            and endpoint_id
        )

        RUNPOD_CONFIGURED.set(
            1 if configured else 0
        )

        if not configured:
            return DependencyHealthResponse(
                name="runpod",
                status="not_configured",
                required=False,
                message=(
                    "RunPod API key or endpoint ID "
                    "is not configured."
                ),
                details={
                    "endpoint_id_configured": bool(
                        endpoint_id
                    ),
                    "api_key_configured": bool(
                        api_key
                    ),
                },
            )

        if not perform_remote_check:
            return DependencyHealthResponse(
                name="runpod",
                status="configured",
                required=False,
                message=(
                    "RunPod is configured. "
                    "Remote health check was skipped."
                ),
                details={
                    "endpoint_id": endpoint_id,
                },
            )

        started_at = time.perf_counter()

        try:
            result = (
                runpod_serverless_adapter_service
                .health(
                    db,
                    endpoint_id=endpoint_id,
                )
            )

            duration = (
                time.perf_counter()
                - started_at
            )

            RUNPOD_HEALTH_CHECK_DURATION_SECONDS.labels(
                endpoint_id=endpoint_id
            ).observe(duration)

            available = bool(
                result.get("available")
            )

            RUNPOD_AVAILABLE.labels(
                endpoint_id=endpoint_id
            ).set(
                1 if available else 0
            )

            return DependencyHealthResponse(
                name="runpod",
                status=(
                    "healthy"
                    if available
                    else "unavailable"
                ),
                required=False,
                latency_ms=round(
                    duration * 1000,
                    3,
                ),
                message=(
                    "RunPod endpoint is available."
                    if available
                    else str(
                        result.get(
                            "error",
                            "RunPod is unavailable.",
                        )
                    )
                ),
                details={
                    "endpoint_id": endpoint_id,
                },
            )

        except Exception as error:
            duration = (
                time.perf_counter()
                - started_at
            )

            RUNPOD_HEALTH_CHECK_DURATION_SECONDS.labels(
                endpoint_id=endpoint_id
            ).observe(duration)

            RUNPOD_AVAILABLE.labels(
                endpoint_id=endpoint_id
            ).set(0)

            return DependencyHealthResponse(
                name="runpod",
                status="unavailable",
                required=False,
                latency_ms=round(
                    duration * 1000,
                    3,
                ),
                message=str(error),
                details={
                    "endpoint_id": endpoint_id,
                },
            )

    def dependencies(
        self,
        db: Session,
        *,
        include_optional: bool,
        perform_remote_checks: bool,
    ) -> list[DependencyHealthResponse]:
        results = [
            self._postgres_health(db),
            self._redis_health(),
            self._storage_health(),
        ]

        if include_optional:
            results.extend(
                [
                    self._comfyui_health(),
                    self._runpod_health(
                        db,
                        perform_remote_check=(
                            perform_remote_checks
                        ),
                    ),
                ]
            )

        for dependency in results:
            DEPENDENCY_HEALTH.labels(
                dependency=dependency.name,
                required=str(
                    dependency.required
                ).lower(),
            ).set(
                1
                if dependency.status
                in {
                    "healthy",
                    "configured",
                    "not_configured",
                }
                else 0
            )

        return results

    def readiness(
        self,
        db: Session,
    ) -> ReadinessResponse:
        dependencies = self.dependencies(
            db,
            include_optional=False,
            perform_remote_checks=False,
        )

        ready = all(
            dependency.status == "healthy"
            for dependency in dependencies
            if dependency.required
        )

        APPLICATION_READY.set(
            1 if ready else 0
        )

        return ReadinessResponse(
            status=(
                "ready"
                if ready
                else "not_ready"
            ),
            ready=ready,
            dependencies=dependencies,
            checked_at=utc_now(),
        )

    def full_health(
        self,
        db: Session,
        *,
        perform_remote_checks: bool,
    ) -> SystemHealthResponse:
        dependencies = self.dependencies(
            db,
            include_optional=True,
            perform_remote_checks=(
                perform_remote_checks
            ),
        )

        required_unhealthy = [
            dependency
            for dependency in dependencies
            if (
                dependency.required
                and dependency.status
                != "healthy"
            )
        ]

        optional_unhealthy = [
            dependency
            for dependency in dependencies
            if (
                not dependency.required
                and dependency.status
                == "unavailable"
            )
        ]

        ready = not required_unhealthy

        APPLICATION_READY.set(
            1 if ready else 0
        )

        APPLICATION_LIVE.set(1)

        if required_unhealthy:
            status = "unhealthy"
        elif optional_unhealthy:
            status = "degraded"
        else:
            status = "healthy"

        return SystemHealthResponse(
            status=status,
            ready=ready,
            live=True,
            service=str(
                self._setting(
                    "APP_NAME",
                    "tryon-backend",
                )
            ),
            version=str(
                self._setting(
                    "APP_VERSION",
                    "1.0.0",
                )
            ),
            environment=str(
                self._setting(
                    "ENVIRONMENT",
                    "development",
                )
            ),
            dependencies=dependencies,
            summary={
                "total": len(dependencies),
                "healthy": sum(
                    1
                    for dependency
                    in dependencies
                    if dependency.status
                    == "healthy"
                ),
                "unavailable": sum(
                    1
                    for dependency
                    in dependencies
                    if dependency.status
                    == "unavailable"
                ),
                "not_configured": sum(
                    1
                    for dependency
                    in dependencies
                    if dependency.status
                    == "not_configured"
                ),
            },
            checked_at=utc_now(),
        )


application_health_service = (
    ApplicationHealthService()
)