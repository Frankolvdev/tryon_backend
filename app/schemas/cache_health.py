from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CacheMemoryMetrics(BaseModel):
    used_memory_bytes: int
    used_memory_human: str | None = None

    used_memory_peak_bytes: int
    used_memory_peak_human: str | None = None

    maxmemory_bytes: int
    maxmemory_human: str | None = None

    memory_fragmentation_ratio: float | None = None


class CacheConnectionMetrics(BaseModel):
    connected_clients: int
    blocked_clients: int
    total_connections_received: int
    rejected_connections: int


class CacheCommandMetrics(BaseModel):
    total_commands_processed: int
    instantaneous_ops_per_second: int

    keyspace_hits: int
    keyspace_misses: int
    hit_rate: float


class CacheKeyspaceDatabaseMetrics(BaseModel):
    database: str
    keys: int
    expires: int
    average_ttl_ms: int | None = None


class CacheServerMetrics(BaseModel):
    redis_version: str | None = None
    redis_mode: str | None = None
    uptime_seconds: int

    role: str | None = None

    maxmemory_policy: str | None = None
    recommended_maxmemory_policy: str

    memory: CacheMemoryMetrics
    connections: CacheConnectionMetrics
    commands: CacheCommandMetrics

    databases: list[
        CacheKeyspaceDatabaseMetrics
    ] = Field(default_factory=list)

    generated_at: datetime


class CacheHealthCheckResponse(BaseModel):
    status: str
    redis_available: bool
    latency_ms: float | None = None

    read_write_test: bool
    expiration_test: bool
    tag_invalidation_test: bool

    configured_policy: str | None = None
    recommended_policy: str

    warnings: list[str] = Field(
        default_factory=list
    )

    details: dict[str, Any] = Field(
        default_factory=dict
    )

    checked_at: datetime


class CacheTtlPolicyResponse(BaseModel):
    default_ttl_seconds: int

    negative_cache_ttl_seconds: int
    active_job_progress_ttl_seconds: int
    terminal_job_progress_ttl_seconds: int

    namespace_ttls: dict[str, int]


class CacheMaintenanceRequest(BaseModel):
    clean_orphan_tag_members: bool = True
    clean_empty_tag_sets: bool = True
    delete_namespace: str | None = None

    scan_count: int = Field(
        default=500,
        ge=10,
        le=5000,
    )

    max_tag_sets: int = Field(
        default=1000,
        ge=1,
        le=10000,
    )


class CacheMaintenanceResponse(BaseModel):
    success: bool

    scanned_tag_sets: int
    orphan_members_removed: int
    empty_tag_sets_deleted: int

    namespace_deleted: str | None = None
    namespace_deleted_keys: int = 0

    errors: list[dict[str, Any]] = Field(
        default_factory=list
    )

    started_at: datetime
    completed_at: datetime