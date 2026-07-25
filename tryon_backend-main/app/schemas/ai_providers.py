from typing import Literal

from pydantic import BaseModel, Field


AiExecutionMode = Literal[
    "simulated",
    "comfyui_local",
    "runpod_serverless",
    "auto",
]


class AiProviderHealth(BaseModel):
    provider: str
    enabled: bool
    available: bool
    configured: bool
    message: str | None = None
    details: dict = Field(default_factory=dict)


class AiProvidersOverview(BaseModel):
    execution_mode: AiExecutionMode
    selected_provider: str
    fallback_order: list[str]
    providers: list[AiProviderHealth]


class AiExecutionModeUpdate(BaseModel):
    execution_mode: AiExecutionMode


class AiProviderActionResponse(BaseModel):
    success: bool
    provider: str
    message: str
    job_id: int | None = None
    status: str | None = None
