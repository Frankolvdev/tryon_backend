from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import ScheduledJobRunStatus, ScheduledJobStatus


class ScheduledJobCreate(BaseModel):
    key: str
    name: str
    description: str | None = None
    cron_expression: str
    status: ScheduledJobStatus = ScheduledJobStatus.ACTIVE
    is_system: bool = False


class ScheduledJobUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    cron_expression: str | None = None
    status: ScheduledJobStatus | None = None


class ScheduledJobResponse(BaseModel):
    id: int
    key: str
    name: str
    description: str | None
    cron_expression: str
    status: ScheduledJobStatus
    is_system: bool
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScheduledJobRunResponse(BaseModel):
    id: int
    scheduled_job_id: int
    status: ScheduledJobRunStatus
    started_at: datetime | None
    finished_at: datetime | None
    output: str | None
    error_message: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ManualRunRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)