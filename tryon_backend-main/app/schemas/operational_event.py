from datetime import datetime
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


OperationalSeverity = Literal[
    "info",
    "warning",
    "error",
    "critical",
]


class OperationalEventCreate(BaseModel):
    event_type: str = Field(
        min_length=2,
        max_length=150,
    )

    source: str = Field(
        min_length=2,
        max_length=100,
    )

    severity: OperationalSeverity

    message: str = Field(
        min_length=1,
        max_length=10000,
    )

    correlation_id: str | None = Field(
        default=None,
        max_length=128,
    )

    user_id: int | None = None
    background_job_id: int | None = None
    tryon_job_id: int | None = None

    provider_job_id: str | None = Field(
        default=None,
        max_length=255,
    )

    exception_type: str | None = Field(
        default=None,
        max_length=255,
    )

    exception_message: str | None = None

    details: dict[str, Any] = Field(
        default_factory=dict,
    )


class OperationalEventResponse(BaseModel):
    id: int

    event_type: str
    source: str
    severity: str
    message: str

    correlation_id: str | None

    user_id: int | None
    background_job_id: int | None
    tryon_job_id: int | None
    provider_job_id: str | None

    exception_type: str | None
    exception_message: str | None

    details: dict[str, Any]

    is_resolved: bool
    resolved_by_user_id: int | None
    resolved_at: datetime | None
    resolution_note: str | None

    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class OperationalEventListResponse(BaseModel):
    items: list[OperationalEventResponse]

    total: int
    skip: int
    limit: int


class OperationalEventResolveRequest(BaseModel):
    resolution_note: str = Field(
        min_length=2,
        max_length=5000,
    )


class OperationalEventSummaryResponse(BaseModel):
    total: int
    unresolved: int

    info: int
    warnings: int
    errors: int
    critical: int

    by_source: dict[str, int]

    generated_at: datetime