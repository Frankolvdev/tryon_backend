from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.common.enums import QualityMode, TryOnItemType, TryOnJobStatus


class TryOnCreateResponse(BaseModel):
    id: int
    status: TryOnJobStatus
    tokens_cost: int
    item_type: TryOnItemType
    quality_mode: QualityMode
    estimated_gpu_seconds: int | None
    estimated_gpu_cost_cents: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TryOnJobResponse(BaseModel):
    id: int
    user_id: int
    person_image_file_id: int
    item_image_file_id: int
    result_file_id: int | None
    pricing_rule_id: int | None
    runpod_config_id: int | None
    item_type: TryOnItemType
    quality_mode: QualityMode
    status: TryOnJobStatus
    tokens_cost: int
    estimated_gpu_seconds: int | None
    estimated_gpu_cost_cents: int | None
    actual_gpu_seconds: int | None
    actual_gpu_cost_cents: int | None
    prompt: str | None
    error_message: str | None
    runpod_job_id: str | None
    comfy_workflow_name: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class TryOnJobAdminUpdate(BaseModel):
    status: TryOnJobStatus | None = None
    error_message: str | None = None
    runpod_job_id: str | None = None
    comfy_workflow_name: str | None = None
    actual_gpu_seconds: int | None = None
    actual_gpu_cost_cents: int | None = None