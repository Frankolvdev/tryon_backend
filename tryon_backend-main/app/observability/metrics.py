from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
)


HTTP_REQUESTS_TOTAL = Counter(
    "tryon_http_requests_total",
    "Total number of HTTP requests.",
    [
        "method",
        "route",
        "status_code",
    ],
)


HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "tryon_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    [
        "method",
        "route",
    ],
    buckets=(
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        30.0,
        60.0,
    ),
)


HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "tryon_http_requests_in_progress",
    "Current HTTP requests being processed.",
    [
        "method",
        "route",
    ],
)


HTTP_RESPONSE_SIZE_BYTES = Histogram(
    "tryon_http_response_size_bytes",
    "HTTP response size in bytes.",
    [
        "method",
        "route",
        "status_code",
    ],
    buckets=(
        100,
        500,
        1000,
        5000,
        10000,
        50000,
        100000,
        500000,
        1000000,
        5000000,
        10000000,
    ),
)


HTTP_EXCEPTIONS_TOTAL = Counter(
    "tryon_http_exceptions_total",
    "Total unhandled HTTP exceptions.",
    [
        "method",
        "route",
        "exception_type",
    ],
)


POSTGRES_AVAILABLE = Gauge(
    "tryon_postgres_available",
    "Whether PostgreSQL is available.",
)


POSTGRES_HEALTH_CHECK_DURATION_SECONDS = Histogram(
    "tryon_postgres_health_check_duration_seconds",
    "Duration of PostgreSQL health checks.",
    buckets=(
        0.001,
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
    ),
)


POSTGRES_POOL_SIZE = Gauge(
    "tryon_postgres_pool_size",
    "Configured SQLAlchemy pool size.",
)


POSTGRES_POOL_CHECKED_OUT = Gauge(
    "tryon_postgres_pool_checked_out",
    "SQLAlchemy connections checked out.",
)


POSTGRES_POOL_CHECKED_IN = Gauge(
    "tryon_postgres_pool_checked_in",
    "SQLAlchemy connections available.",
)


POSTGRES_POOL_OVERFLOW = Gauge(
    "tryon_postgres_pool_overflow",
    "Current SQLAlchemy pool overflow.",
)


REDIS_AVAILABLE = Gauge(
    "tryon_redis_available",
    "Whether Redis is available.",
)


REDIS_USED_MEMORY_BYTES = Gauge(
    "tryon_redis_used_memory_bytes",
    "Redis memory currently in use.",
)


REDIS_CONNECTED_CLIENTS = Gauge(
    "tryon_redis_connected_clients",
    "Clients currently connected to Redis.",
)


REDIS_BLOCKED_CLIENTS = Gauge(
    "tryon_redis_blocked_clients",
    "Redis clients currently blocked.",
)


REDIS_KEYS = Gauge(
    "tryon_redis_keys",
    "Keys stored in Redis.",
    [
        "database",
    ],
)


REDIS_KEYSPACE_HITS_TOTAL = Gauge(
    "tryon_redis_keyspace_hits_total",
    "Redis keyspace hits.",
)


REDIS_KEYSPACE_MISSES_TOTAL = Gauge(
    "tryon_redis_keyspace_misses_total",
    "Redis keyspace misses.",
)


REDIS_EVICTED_KEYS_TOTAL = Gauge(
    "tryon_redis_evicted_keys_total",
    "Keys evicted by Redis.",
)


BACKGROUND_JOBS = Gauge(
    "tryon_background_jobs",
    "Background jobs by queue, status and mode.",
    [
        "queue_name",
        "status",
        "execution_mode",
    ],
)


BACKGROUND_JOB_ATTEMPTS_TOTAL = Counter(
    "tryon_background_job_attempts_total",
    "Background-job attempts started.",
    [
        "queue_name",
        "job_type",
        "execution_mode",
    ],
)


BACKGROUND_JOB_COMPLETIONS_TOTAL = Counter(
    "tryon_background_job_completions_total",
    "Background jobs reaching a terminal state.",
    [
        "queue_name",
        "job_type",
        "execution_mode",
        "status",
    ],
)


BACKGROUND_JOB_DURATION_SECONDS = Histogram(
    "tryon_background_job_duration_seconds",
    "Background-job execution duration.",
    [
        "queue_name",
        "job_type",
        "execution_mode",
        "status",
    ],
    buckets=(
        0.1,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        30.0,
        60.0,
        120.0,
        300.0,
        600.0,
        1200.0,
        1800.0,
        3600.0,
    ),
)


BACKGROUND_JOB_EXPIRED_LEASES = Gauge(
    "tryon_background_job_expired_leases",
    "Background jobs with expired leases.",
)


BACKGROUND_JOB_QUEUE_OLDEST_AGE_SECONDS = Gauge(
    "tryon_background_job_queue_oldest_age_seconds",
    "Age of the oldest waiting job.",
    [
        "queue_name",
    ],
)


WORKER_ACTIVE_JOBS = Gauge(
    "tryon_worker_active_jobs",
    "Jobs currently active in a worker.",
    [
        "worker_name",
        "queue_name",
    ],
)


WORKER_HEARTBEATS_TOTAL = Counter(
    "tryon_worker_heartbeats_total",
    "Heartbeats sent by background workers.",
    [
        "worker_name",
        "queue_name",
    ],
)


WORKER_ERRORS_TOTAL = Counter(
    "tryon_worker_errors_total",
    "Errors encountered by workers.",
    [
        "worker_name",
        "queue_name",
        "error_type",
    ],
)


RUNPOD_CONFIGURED = Gauge(
    "tryon_runpod_configured",
    "Whether RunPod credentials and endpoint are configured.",
)


RUNPOD_AVAILABLE = Gauge(
    "tryon_runpod_available",
    "Whether the configured RunPod endpoint health check succeeds.",
    [
        "endpoint_id",
    ],
)


RUNPOD_HEALTH_CHECK_DURATION_SECONDS = Histogram(
    "tryon_runpod_health_check_duration_seconds",
    "Duration of RunPod endpoint health checks.",
    [
        "endpoint_id",
    ],
    buckets=(
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        30.0,
    ),
)


RUNPOD_SUBMISSIONS_TOTAL = Counter(
    "tryon_runpod_submissions_total",
    "Jobs submitted to RunPod.",
    [
        "endpoint_id",
    ],
)


RUNPOD_COMPLETIONS_TOTAL = Counter(
    "tryon_runpod_completions_total",
    "RunPod jobs reaching a terminal state.",
    [
        "endpoint_id",
        "status",
    ],
)


RUNPOD_EXECUTION_DURATION_SECONDS = Histogram(
    "tryon_runpod_execution_duration_seconds",
    "Execution time reported by RunPod.",
    [
        "endpoint_id",
    ],
    buckets=(
        1.0,
        2.5,
        5.0,
        10.0,
        20.0,
        30.0,
        60.0,
        120.0,
        300.0,
        600.0,
        1200.0,
        1800.0,
    ),
)


RUNPOD_QUEUE_DELAY_SECONDS = Histogram(
    "tryon_runpod_queue_delay_seconds",
    "Queue delay reported by RunPod.",
    [
        "endpoint_id",
    ],
    buckets=(
        0.1,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        30.0,
        60.0,
        120.0,
        300.0,
        600.0,
    ),
)


RUNPOD_JOBS = Gauge(
    "tryon_runpod_jobs",
    "RunPod-backed jobs by endpoint and status.",
    [
        "endpoint_id",
        "status",
    ],
)


COMFYUI_LOCAL_CONFIGURED = Gauge(
    "tryon_comfyui_local_configured",
    "Whether a local ComfyUI URL is configured.",
)


COMFYUI_LOCAL_AVAILABLE = Gauge(
    "tryon_comfyui_local_available",
    "Whether local ComfyUI is available.",
)


COMFYUI_LOCAL_HEALTH_CHECK_DURATION_SECONDS = Histogram(
    "tryon_comfyui_local_health_check_duration_seconds",
    "Duration of local ComfyUI health checks.",
    buckets=(
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
    ),
)


LOCAL_STORAGE_AVAILABLE = Gauge(
    "tryon_local_storage_available",
    "Whether the local storage directory can be accessed.",
)


LOCAL_STORAGE_FREE_BYTES = Gauge(
    "tryon_local_storage_free_bytes",
    "Free bytes on the local storage filesystem.",
)


LOCAL_STORAGE_TOTAL_BYTES = Gauge(
    "tryon_local_storage_total_bytes",
    "Total bytes on the local storage filesystem.",
)


DEPENDENCY_HEALTH = Gauge(
    "tryon_dependency_health",
    "Health state of an application dependency.",
    [
        "dependency",
        "required",
    ],
)


APPLICATION_READY = Gauge(
    "tryon_application_ready",
    "Whether the application is ready to serve normal traffic.",
)


APPLICATION_LIVE = Gauge(
    "tryon_application_live",
    "Whether the application process is alive.",
)


OBSERVABILITY_COLLECTOR_ERRORS_TOTAL = Counter(
    "tryon_observability_collector_errors_total",
    "Errors while collecting operational metrics.",
    [
        "collector",
        "error_type",
    ],
)