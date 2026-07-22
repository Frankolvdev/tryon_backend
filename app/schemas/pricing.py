from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import PricingOperationType, QualityMode, TryOnItemType


class CommercialSettingsResponse(BaseModel):
    token_value_usd: float = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)


class CommercialSettingsUpdate(BaseModel):
    token_value_usd: float = Field(gt=0, le=1000)
    currency: str = Field(min_length=3, max_length=3)


class CommercialPricePreviewRequest(BaseModel):
    average_execution_cost_usd: float = Field(ge=0)
    desired_profit_percent: float = Field(ge=0, le=10000)


class CommercialPricePreviewResponse(BaseModel):
    average_execution_cost_usd: float
    desired_profit_percent: float
    token_value_usd: float
    currency: str
    final_price_usd: float
    required_tokens: int
    effective_margin_percent: float


class PricingRuleCreate(BaseModel):
    operation_type: PricingOperationType = PricingOperationType.TRYON
    item_type: TryOnItemType
    quality_mode: QualityMode = QualityMode.STANDARD
    generation_module_id: int | None = Field(default=None, ge=1)
    average_execution_cost_usd: float = Field(ge=0)
    desired_profit_percent: float = Field(default=70, ge=0, le=10000)
    is_active: bool = True


class PricingRuleUpdate(BaseModel):
    generation_module_id: int | None = Field(default=None, ge=1)
    average_execution_cost_usd: float | None = Field(default=None, ge=0)
    desired_profit_percent: float | None = Field(default=None, ge=0, le=10000)
    is_active: bool | None = None


class PricingRuleResponse(BaseModel):
    id: int
    operation_type: PricingOperationType
    item_type: TryOnItemType
    quality_mode: QualityMode
    generation_module_id: int | None
    average_execution_cost_usd: float
    desired_profit_percent: float
    final_price_usd: float
    required_tokens: int
    effective_margin_percent: float
    token_value_usd: float
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PricingEstimateResponse(BaseModel):
    operation_type: PricingOperationType
    item_type: TryOnItemType
    quality_mode: QualityMode
    tokens_cost: int
    final_price_usd: float
    currency: str
