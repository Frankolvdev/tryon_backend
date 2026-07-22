from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.common.generation_module_enums import GenerationExecutionEngine


class GenerationModuleExecutionCreate(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)
    engine: GenerationExecutionEngine | None = None


class GenerationModuleExecutionLog(BaseModel):
    timestamp: datetime
    level: Literal["info", "warning", "error"] = "info"
    step_key: str | None = None
    message: str


class GenerationModuleStepExecution(BaseModel):
    step_key: str
    step_name: str
    step_type: str
    status: Literal["pending", "running", "completed", "failed", "cancelled"]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    outputs: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class GenerationModuleExecutionResponse(BaseModel):
    id: UUID
    module_id: int
    module_key: str
    user_id: int | None = None
    engine: GenerationExecutionEngine
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    progress: int = Field(ge=0, le=100)
    inputs: dict[str, Any]
    context: dict[str, Any]
    outputs: dict[str, Any]
    steps: list[GenerationModuleStepExecution]
    logs: list[GenerationModuleExecutionLog]
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    cancel_requested: bool = False
    pricing_rule_id: int | None = None
    tokens_charged: int = 0
    tokens_refunded: bool = False
    currency: str | None = None
    commercial_price: float | None = None
    queue_name: str | None = None
    queue_position: int | None = None
    provider_status: str | None = None
    provider_job_id: str | None = None
    provider_endpoint_id: str | None = None
    dispatch_attempts: int = 0
    heartbeat_at: datetime | None = None
