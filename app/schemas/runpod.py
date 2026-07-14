from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import RunPodMode


class RunPodConfigCreate(BaseModel):
    name: str
    mode: RunPodMode = RunPodMode.SERVERLESS
    endpoint_id: str | None = None
    endpoint_url: str | None = None
    gpu_type: str | None = None
    docker_image: str | None = None
    comfy_workflow_name: str | None = None
    min_workers: int = Field(default=0, ge=0)
    max_workers: int = Field(default=3, ge=1)
    estimated_cost_per_second_cents: int = Field(default=1, ge=0)
    is_active: bool = True


class RunPodConfigUpdate(BaseModel):
    name: str | None = None
    endpoint_id: str | None = None
    endpoint_url: str | None = None
    gpu_type: str | None = None
    docker_image: str | None = None
    comfy_workflow_name: str | None = None
    min_workers: int | None = Field(default=None, ge=0)
    max_workers: int | None = Field(default=None, ge=1)
    estimated_cost_per_second_cents: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class RunPodConfigResponse(BaseModel):
    id: int
    name: str
    mode: RunPodMode
    endpoint_id: str | None
    endpoint_url: str | None
    gpu_type: str | None
    docker_image: str | None
    comfy_workflow_name: str | None
    min_workers: int
    max_workers: int
    estimated_cost_per_second_cents: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)