from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class QueueStatusMetric(BaseModel):
    status: str
    total: int


class QueueNameMetric(BaseModel):
    queue_name: str
    total: int


class ExecutionModeMetric(BaseModel):
    execution_mode: str
    total: int


class BackgroundJobMetricsResponse(BaseModel):
    total_jobs: int

    queued_jobs: int
    running_jobs: int
    succeeded_jobs: int
    failed_jobs: int
    retrying_jobs: int
    dead_letter_jobs: int
    canceled_jobs: int

    expired_leases: int

    average_duration_seconds: float | None
    average_attempts: float | None

    jobs_by_status: list[QueueStatusMetric]
    jobs_by_queue: list[QueueNameMetric]
    jobs_by_execution_mode: list[
        ExecutionModeMetric
    ]

    period_start: datetime
    period_end: datetime
    generated_at: datetime


class BackgroundJobMaintenanceRequest(BaseModel):
    recover_expired_leases: bool = True
    signal_ready_queues: bool = True

    max_items: int = Field(
        default=1000,
        ge=1,
        le=10000,
    )


class BackgroundJobMaintenanceResponse(BaseModel):
    success: bool

    expired_leases_inspected: int
    recovered_jobs: int
    dead_lettered_jobs: int

    signaled_queues: list[str]

    errors: list[dict[str, Any]] = Field(
        default_factory=list,
    )

    started_at: datetime
    completed_at: datetime