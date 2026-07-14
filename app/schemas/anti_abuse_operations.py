from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AntiAbuseEventTypeMetric(BaseModel):
    event_type: str
    total: int


class AntiAbuseSeverityMetric(BaseModel):
    severity: str
    total: int


class AntiAbuseStatusMetric(BaseModel):
    status: str
    total: int


class AntiAbuseMetricsResponse(BaseModel):
    total_events: int
    open_events: int
    reviewed_events: int
    resolved_events: int
    ignored_events: int

    low_severity_events: int
    medium_severity_events: int
    high_severity_events: int
    critical_severity_events: int

    active_blocks: int
    temporary_blocks: int
    permanent_blocks: int
    expired_active_blocks: int

    enabled_policies: int
    disabled_policies: int

    events_by_type: list[AntiAbuseEventTypeMetric]
    events_by_severity: list[AntiAbuseSeverityMetric]
    events_by_status: list[AntiAbuseStatusMetric]

    period_start: datetime
    period_end: datetime
    generated_at: datetime


class AntiAbuseValidationItem(BaseModel):
    key: str
    valid: bool
    required: bool
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AntiAbuseValidationResponse(BaseModel):
    ready: bool
    redis_available: bool
    checks: list[AntiAbuseValidationItem]
    checked_at: datetime


class AntiAbuseCleanupRequest(BaseModel):
    deactivate_expired_blocks: bool = True

    delete_old_resolved_events: bool = False

    resolved_event_retention_days: int = Field(
        default=180,
        ge=30,
        le=3650,
    )

    max_items: int = Field(
        default=1000,
        ge=1,
        le=10000,
    )


class AntiAbuseCleanupTaskResult(BaseModel):
    task: str
    processed: int
    succeeded: int
    failed: int
    skipped: int
    errors: list[dict[str, Any]] = Field(default_factory=list)


class AntiAbuseCleanupResponse(BaseModel):
    started_at: datetime
    completed_at: datetime

    tasks: list[AntiAbuseCleanupTaskResult]

    total_processed: int
    total_succeeded: int
    total_failed: int
    total_skipped: int

    success: bool


class AntiAbuseJobRunRequest(BaseModel):
    max_items: int = Field(
        default=1000,
        ge=1,
        le=10000,
    )


class AntiAbuseJobResult(BaseModel):
    job_name: str
    started_at: datetime
    completed_at: datetime

    processed: int
    succeeded: int
    failed: int
    skipped: int

    success: bool
    errors: list[dict[str, Any]] = Field(default_factory=list)


class AntiAbuseJobCatalogItem(BaseModel):
    name: str
    description: str
    recommended_schedule: str
    enabled: bool


class AntiAbuseJobCatalogResponse(BaseModel):
    jobs: list[AntiAbuseJobCatalogItem]