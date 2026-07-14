from datetime import datetime
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.common.job_enums import (
    JobAttemptStatus,
    JobDependencyType,
    JobExecutionMode,
    JobPriority,
    JobQueueName,
    JobStatus,
)


class BackgroundJobDependencyCreate(BaseModel):
    depends_on_job_id: int

    dependency_type: JobDependencyType = (
        JobDependencyType.SUCCESS
    )


class BackgroundJobCreate(BaseModel):
    job_type: str = Field(
        min_length=2,
        max_length=200,
    )

    queue_name: JobQueueName = JobQueueName.DEFAULT

    execution_mode: JobExecutionMode = (
        JobExecutionMode.INTERNAL
    )

    priority: JobPriority = JobPriority.NORMAL

    user_id: int | None = None
    tryon_job_id: int | None = None
    external_ai_job_id: int | None = None

    idempotency_key: str | None = Field(
        default=None,
        min_length=3,
        max_length=255,
    )

    payload: dict[str, Any] = Field(
        default_factory=dict,
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )

    dependencies: list[
        BackgroundJobDependencyCreate
    ] = Field(default_factory=list)

    max_attempts: int = Field(
        default=3,
        ge=1,
        le=100,
    )

    retry_backoff_seconds: int = Field(
        default=30,
        ge=0,
        le=86400,
    )

    retry_backoff_multiplier: float = Field(
        default=2.0,
        ge=1.0,
        le=10.0,
    )

    timeout_seconds: int = Field(
        default=900,
        ge=1,
        le=86400,
    )

    scheduled_at: datetime | None = None
    is_cancelable: bool = True
    retain_until: datetime | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if (
            self.retain_until is not None
            and self.scheduled_at is not None
            and self.retain_until <= self.scheduled_at
        ):
            raise ValueError(
                "retain_until must be later than scheduled_at."
            )

        dependency_ids = [
            item.depends_on_job_id
            for item in self.dependencies
        ]

        if len(dependency_ids) != len(set(dependency_ids)):
            raise ValueError(
                "Duplicate job dependencies are not allowed."
            )

        return self


class UserBackgroundJobCreate(BaseModel):
    job_type: str = Field(
        min_length=2,
        max_length=200,
    )

    queue_name: JobQueueName = JobQueueName.DEFAULT

    execution_mode: JobExecutionMode = (
        JobExecutionMode.INTERNAL
    )

    priority: JobPriority = JobPriority.NORMAL

    tryon_job_id: int | None = None

    idempotency_key: str | None = Field(
        default=None,
        min_length=3,
        max_length=255,
    )

    payload: dict[str, Any] = Field(
        default_factory=dict,
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )

    dependencies: list[
        BackgroundJobDependencyCreate
    ] = Field(default_factory=list)

    max_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
    )

    retry_backoff_seconds: int = Field(
        default=30,
        ge=0,
        le=3600,
    )

    retry_backoff_multiplier: float = Field(
        default=2.0,
        ge=1.0,
        le=5.0,
    )

    timeout_seconds: int = Field(
        default=900,
        ge=1,
        le=7200,
    )

    scheduled_at: datetime | None = None
    is_cancelable: bool = True

    @model_validator(mode="after")
    def validate_dependencies(self):
        dependency_ids = [
            item.depends_on_job_id
            for item in self.dependencies
        ]

        if len(dependency_ids) != len(set(dependency_ids)):
            raise ValueError(
                "Duplicate job dependencies are not allowed."
            )

        return self


class BackgroundJobResponse(BaseModel):
    id: int
    public_id: str

    job_type: str
    queue_name: JobQueueName
    execution_mode: JobExecutionMode
    status: JobStatus
    priority: int

    user_id: int | None
    tryon_job_id: int | None
    external_ai_job_id: int | None

    idempotency_key: str | None

    payload: dict[str, Any]
    result: dict[str, Any] | None
    metadata: dict[str, Any]

    error_code: str | None
    error_message: str | None
    error_details: dict[str, Any]

    progress: float
    progress_message: str | None

    attempt_count: int
    max_attempts: int

    retry_backoff_seconds: int
    retry_backoff_multiplier: float
    timeout_seconds: int

    scheduled_at: datetime | None
    available_at: datetime

    queued_at: datetime | None
    claimed_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    canceled_at: datetime | None
    cancel_requested_at: datetime | None

    last_heartbeat_at: datetime | None

    lease_owner: str | None
    lease_expires_at: datetime | None

    provider_job_id: str | None
    provider_endpoint_id: str | None

    worker_name: str | None
    worker_version: str | None

    is_cancelable: bool
    retain_until: datetime | None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BackgroundJobListResponse(BaseModel):
    items: list[BackgroundJobResponse]
    total: int
    skip: int
    limit: int


class BackgroundJobDependencyResponse(BaseModel):
    id: int
    background_job_id: int
    depends_on_job_id: int
    dependency_type: JobDependencyType
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BackgroundJobDependencyListResponse(BaseModel):
    items: list[BackgroundJobDependencyResponse]
    total: int


class BackgroundJobProgressUpdate(BaseModel):
    progress: float = Field(
        ge=0.0,
        le=100.0,
    )

    message: str | None = Field(
        default=None,
        max_length=500,
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )


class BackgroundJobCancelRequest(BaseModel):
    reason: str | None = Field(
        default=None,
        max_length=1000,
    )


class BackgroundJobCancelResponse(BaseModel):
    job: BackgroundJobResponse
    cancellation_requested: bool
    canceled_immediately: bool
    message: str


class BackgroundJobRetryRequest(BaseModel):
    reset_attempt_count: bool = False

    priority: JobPriority | None = None

    scheduled_at: datetime | None = None

    reason: str | None = Field(
        default=None,
        max_length=1000,
    )


class BackgroundJobRetryResponse(BaseModel):
    job: BackgroundJobResponse
    retried: bool
    message: str


class BackgroundJobAttemptResponse(BaseModel):
    id: int
    background_job_id: int
    attempt_number: int
    status: JobAttemptStatus

    worker_name: str | None
    provider_job_id: str | None

    started_at: datetime
    completed_at: datetime | None
    duration_seconds: float | None

    error_code: str | None
    error_message: str | None
    error_details: dict[str, Any]

    result: dict[str, Any] | None
    metrics: dict[str, Any]

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BackgroundJobAttemptListResponse(BaseModel):
    items: list[BackgroundJobAttemptResponse]
    total: int


class BackgroundJobDetailResponse(BaseModel):
    job: BackgroundJobResponse

    attempts: list[BackgroundJobAttemptResponse]

    dependencies: list[
        BackgroundJobDependencyResponse
    ]

    dependents: list[
        BackgroundJobDependencyResponse
    ]