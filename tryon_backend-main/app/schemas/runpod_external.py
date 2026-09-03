from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class RunPodSubmitRequest(BaseModel):
    endpoint_id: str
    input: dict[str, Any]
    internal_job_type: str = "manual"
    internal_job_id: int | None = None


class RunPodSubmitResponse(BaseModel):
    external_ai_job_id: int
    provider_job_id: str | None
    status: str
    raw_response: dict[str, Any]


class RunPodStatusResponse(BaseModel):
    external_ai_job_id: int
    provider_job_id: str | None
    status: str
    raw_response: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error_message: str | None = None


class RunPodCancelRequest(BaseModel):
    endpoint_id: str


class RunPodCancelResponse(BaseModel):
    external_ai_job_id: int
    provider_job_id: str | None
    status: str
    raw_response: dict[str, Any] | None = None


class RunPodCallbackRequest(BaseModel):
    id: str | None = None
    status: str
    output: dict[str, Any] | None = None
    error: str | None = None
    executionTime: int | None = None
    delayTime: int | None = None


class RunPodCallbackResponse(BaseModel):
    received: bool
    provider_job_id: str | None
    status: str
    message: str


class ExternalAiJobResponse(BaseModel):
    id: int
    provider: str
    provider_job_id: str | None
    internal_job_type: str
    internal_job_id: int | None
    status: str
    request: dict[str, Any] | None
    response: dict[str, Any] | None
    result: dict[str, Any] | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)