from datetime import datetime

from pydantic import BaseModel, Field


class OperationalEventRetentionRequest(BaseModel):
    delete_resolved_older_than_days: int = Field(
        default=30,
        ge=1,
        le=3650,
    )

    delete_info_older_than_days: int = Field(
        default=14,
        ge=1,
        le=3650,
    )

    delete_warning_older_than_days: int = Field(
        default=90,
        ge=1,
        le=3650,
    )

    delete_error_older_than_days: int = Field(
        default=365,
        ge=1,
        le=3650,
    )

    preserve_unresolved_errors: bool = True
    preserve_unresolved_critical: bool = True

    batch_size: int = Field(
        default=1000,
        ge=1,
        le=10000,
    )


class OperationalEventRetentionResponse(BaseModel):
    success: bool

    resolved_deleted: int
    info_deleted: int
    warnings_deleted: int
    errors_deleted: int
    total_deleted: int

    started_at: datetime
    completed_at: datetime

    errors: list[str] = Field(
        default_factory=list,
    )


class ObservabilitySelfTestResponse(BaseModel):
    success: bool

    prometheus_registry_available: bool
    postgres_available: bool
    redis_available: bool
    operational_event_created: bool
    operational_event_deleted: bool

    details: dict = Field(
        default_factory=dict,
    )

    checked_at: datetime