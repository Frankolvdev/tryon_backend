from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.background_job import BackgroundJobResponse


class BackgroundJobClaimRequest(BaseModel):
    worker_name: str = Field(
        min_length=2,
        max_length=255,
    )

    worker_version: str | None = Field(
        default=None,
        max_length=100,
    )

    queue_name: str = Field(
        default="default",
        min_length=1,
        max_length=100,
    )

    max_jobs: int = Field(
        default=1,
        ge=1,
        le=20,
    )

    lease_seconds: int = Field(
        default=120,
        ge=30,
        le=3600,
    )


class BackgroundJobClaimedItem(BaseModel):
    job: BackgroundJobResponse
    lease_token: str
    attempt_id: int
    attempt_number: int


class BackgroundJobClaimResponse(BaseModel):
    items: list[BackgroundJobClaimedItem]
    claimed: int
    queue_name: str
    worker_name: str


class BackgroundJobStartRequest(BaseModel):
    worker_name: str = Field(
        min_length=2,
        max_length=255,
    )

    lease_token: str = Field(
        min_length=16,
        max_length=255,
    )


class BackgroundJobHeartbeatRequest(BaseModel):
    worker_name: str = Field(
        min_length=2,
        max_length=255,
    )

    lease_token: str = Field(
        min_length=16,
        max_length=255,
    )

    lease_seconds: int = Field(
        default=120,
        ge=30,
        le=3600,
    )

    progress: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
    )

    progress_message: str | None = Field(
        default=None,
        max_length=500,
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )


class BackgroundJobHeartbeatResponse(BaseModel):
    job_id: int
    public_id: str
    status: str

    lease_expires_at: datetime
    cancel_requested: bool

    progress: float
    progress_message: str | None


class BackgroundJobQueueSignalResponse(BaseModel):
    queue_name: str
    signaled: bool
    redis_available: bool


class BackgroundJobRecoveryResponse(BaseModel):
    inspected: int
    recovered: int
    dead_lettered: int
    failed: int
    errors: list[dict[str, Any]] = Field(
        default_factory=list,
    )