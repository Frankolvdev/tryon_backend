import time
from uuid import uuid4

from redis.exceptions import RedisError

from app.common.cache_enums import (
    CacheNamespace,
)
from app.common.time import utc_now
from app.core.redis_client import redis_client
from app.schemas.cache_health import (
    CacheHealthCheckResponse,
    CacheTtlPolicyResponse,
)
from app.services.cache_server_metrics_service import (
    cache_server_metrics_service,
)
from app.services.cache_ttl_policy_service import (
    cache_ttl_policy_service,
)
from app.services.distributed_cache_service import (
    distributed_cache_service,
)


class CacheHealthService:
    RECOMMENDED_MAXMEMORY_POLICY = (
        "allkeys-lru"
    )

    def ttl_policies(
        self,
    ) -> CacheTtlPolicyResponse:
        return CacheTtlPolicyResponse(
            default_ttl_seconds=(
                cache_ttl_policy_service
                .DEFAULT_TTL_SECONDS
            ),
            negative_cache_ttl_seconds=(
                cache_ttl_policy_service
                .NEGATIVE_CACHE_TTL_SECONDS
            ),
            active_job_progress_ttl_seconds=(
                cache_ttl_policy_service
                .ACTIVE_JOB_PROGRESS_TTL_SECONDS
            ),
            terminal_job_progress_ttl_seconds=(
                cache_ttl_policy_service
                .TERMINAL_JOB_PROGRESS_TTL_SECONDS
            ),
            namespace_ttls=(
                cache_ttl_policy_service
                .all_policies()
            ),
        )

    def run_health_check(
        self,
    ) -> CacheHealthCheckResponse:
        checked_at = utc_now()
        test_identifier = uuid4().hex

        redis_available = False
        latency_ms: float | None = None

        read_write_test = False
        expiration_test = False
        tag_invalidation_test = False

        warnings: list[str] = []
        details: dict = {}

        try:
            client = redis_client.get_client()

            started_at = time.perf_counter()
            redis_available = bool(
                client.ping()
            )

            latency_ms = round(
                (
                    time.perf_counter()
                    - started_at
                )
                * 1000,
                3,
            )

        except RedisError as error:
            warnings.append(
                "Redis ping failed."
            )

            details[
                "ping_error"
            ] = str(error)

        if redis_available:
            try:
                set_result = (
                    distributed_cache_service
                    .set(
                        namespace=(
                            CacheNamespace.SYSTEM
                        ),
                        parts=[
                            "health-check",
                            test_identifier,
                        ],
                        value={
                            "working": True,
                            "id": test_identifier,
                        },
                        ttl_seconds=10,
                        tags=[
                            (
                                "cache-health:"
                                f"{test_identifier}"
                            )
                        ],
                    )
                )

                get_result = (
                    distributed_cache_service
                    .get(
                        namespace=(
                            CacheNamespace.SYSTEM
                        ),
                        parts=[
                            "health-check",
                            test_identifier,
                        ],
                    )
                )

                read_write_test = bool(
                    set_result.stored
                    and get_result.found
                    and isinstance(
                        get_result.value,
                        dict,
                    )
                    and get_result.value.get(
                        "working"
                    )
                    is True
                )

                expiration_key = (
                    distributed_cache_service
                    .set(
                        namespace=(
                            CacheNamespace.SYSTEM
                        ),
                        parts=[
                            "expiration-check",
                            test_identifier,
                        ],
                        value=True,
                        ttl_seconds=1,
                    )
                )

                if expiration_key.stored:
                    time.sleep(1.1)

                    expiration_result = (
                        distributed_cache_service
                        .get(
                            namespace=(
                                CacheNamespace.SYSTEM
                            ),
                            parts=[
                                "expiration-check",
                                test_identifier,
                            ],
                        )
                    )

                    expiration_test = (
                        not expiration_result.found
                    )

                invalidation = (
                    distributed_cache_service
                    .invalidate_tag(
                        tag=(
                            "cache-health:"
                            f"{test_identifier}"
                        )
                    )
                )

                after_invalidation = (
                    distributed_cache_service
                    .get(
                        namespace=(
                            CacheNamespace.SYSTEM
                        ),
                        parts=[
                            "health-check",
                            test_identifier,
                        ],
                    )
                )

                tag_invalidation_test = (
                    invalidation.deleted_count
                    >= 1
                    and not after_invalidation.found
                )

            except Exception as error:
                warnings.append(
                    "Cache functional test failed."
                )

                details[
                    "functional_test_error"
                ] = str(error)

        configured_policy: str | None = None

        if redis_available:
            try:
                metrics = (
                    cache_server_metrics_service
                    .get_metrics()
                )

                configured_policy = (
                    metrics.maxmemory_policy
                )

                details["server_metrics"] = (
                    metrics.model_dump(
                        mode="json"
                    )
                )

                if (
                    configured_policy
                    != self.RECOMMENDED_MAXMEMORY_POLICY
                ):
                    warnings.append(
                        "Redis maxmemory-policy is "
                        f"'{configured_policy}'. "
                        "For this cache workload, "
                        "'allkeys-lru' is recommended."
                    )

                if metrics.memory.maxmemory_bytes <= 0:
                    warnings.append(
                        "Redis maxmemory is not limited. "
                        "Configure a memory limit in "
                        "production."
                    )

                if (
                    metrics.connections
                    .rejected_connections
                    > 0
                ):
                    warnings.append(
                        "Redis has rejected connections."
                    )

            except Exception as error:
                warnings.append(
                    "Could not read Redis server metrics."
                )

                details[
                    "metrics_error"
                ] = str(error)

        all_tests_ok = (
            redis_available
            and read_write_test
            and expiration_test
            and tag_invalidation_test
        )

        return CacheHealthCheckResponse(
            status=(
                "healthy"
                if all_tests_ok
                else (
                    "degraded"
                    if redis_available
                    else "unavailable"
                )
            ),
            redis_available=redis_available,
            latency_ms=latency_ms,
            read_write_test=read_write_test,
            expiration_test=expiration_test,
            tag_invalidation_test=(
                tag_invalidation_test
            ),
            configured_policy=(
                configured_policy
            ),
            recommended_policy=(
                self.RECOMMENDED_MAXMEMORY_POLICY
            ),
            warnings=warnings,
            details=details,
            checked_at=checked_at,
        )


cache_health_service = CacheHealthService()