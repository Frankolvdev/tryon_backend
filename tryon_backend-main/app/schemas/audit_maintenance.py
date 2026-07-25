from datetime import date, datetime

from pydantic import BaseModel, Field


class AuditRetentionRequest(BaseModel):
    delete_successful_older_than_days: int = Field(
        default=365,
        ge=1,
        le=3650,
    )

    delete_failed_older_than_days: int = Field(
        default=730,
        ge=1,
        le=3650,
    )

    delete_read_events_older_than_days: int = Field(
        default=90,
        ge=1,
        le=3650,
    )

    preserve_restorable_entries: bool = True
    preserve_restore_actions: bool = True
    preserve_failed_entries: bool = True

    batch_size: int = Field(
        default=1000,
        ge=1,
        le=10000,
    )


class AuditRetentionResponse(BaseModel):
    success: bool

    successful_deleted: int
    failed_deleted: int
    read_events_deleted: int

    total_deleted: int

    started_at: datetime
    completed_at: datetime

    errors: list[str] = Field(
        default_factory=list,
    )


class AuditDailyMetric(BaseModel):
    day: date

    total: int
    successful: int
    failed: int
    restorable: int


class AuditGroupMetric(BaseModel):
    key: str
    total: int


class AuditActorMetric(BaseModel):
    actor_user_id: int | None
    actor_email: str | None
    actor_type: str

    total: int
    successful: int
    failed: int


class AuditAdvancedStatisticsResponse(BaseModel):
    period_days: int

    total_entries: int
    successful_entries: int
    failed_entries: int
    restorable_entries: int
    restoration_entries: int

    success_rate: float

    daily: list[AuditDailyMetric]

    top_actions: list[AuditGroupMetric]
    top_entity_types: list[AuditGroupMetric]
    top_actor_types: list[AuditGroupMetric]
    top_actors: list[AuditActorMetric]

    generated_at: datetime


class AuditSelfTestResponse(BaseModel):
    success: bool

    snapshot_test: bool
    redaction_test: bool
    diff_test: bool
    database_create_test: bool
    database_read_test: bool
    database_delete_test: bool

    temporary_audit_entry_id: int | None = None

    details: dict = Field(
        default_factory=dict,
    )

    checked_at: datetime