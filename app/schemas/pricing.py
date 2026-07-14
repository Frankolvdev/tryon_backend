from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import PricingOperationType, QualityMode, TryOnItemType


class PricingRuleCreate(BaseModel):
    operation_type: PricingOperationType = PricingOperationType.TRYON
    item_type: TryOnItemType
    quality_mode: QualityMode = QualityMode.STANDARD
    tokens_cost: int = Field(gt=0)
    estimated_gpu_seconds: int = Field(default=30, ge=0)
    estimated_gpu_cost_cents: int = Field(default=1, ge=0)
    margin_percent: int = Field(default=70, ge=0)
    is_active: bool = True


class PricingRuleUpdate(BaseModel):
    tokens_cost: int | None = Field(default=None, gt=0)
    estimated_gpu_seconds: int | None = Field(default=None, ge=0)
    estimated_gpu_cost_cents: int | None = Field(default=None, ge=0)
    margin_percent: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class PricingRuleResponse(BaseModel):
    id: int
    operation_type: PricingOperationType
    item_type: TryOnItemType
    quality_mode: QualityMode
    tokens_cost: int
    estimated_gpu_seconds: int
    estimated_gpu_cost_cents: int
    margin_percent: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PricingEstimateResponse(BaseModel):
    operation_type: PricingOperationType
    item_type: TryOnItemType
    quality_mode: QualityMode
    tokens_cost: int
    estimated_gpu_seconds: int
    estimated_gpu_cost_cents: int