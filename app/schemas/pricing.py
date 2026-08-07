from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.common.enums import PricingOperationType, QualityMode, TryOnItemType


class CommercialSettingsResponse(BaseModel):
    # Economic base used by generation pricing: AI reserve + protected profit.
    token_value_usd: float = Field(gt=0)
    # Explicit component reserved for non-AI operating expenses. It is zero
    # until the operational cashbox is enabled in MegaZIP 4.
    operational_reserve_per_token_usd: float = Field(default=0, ge=0)
    # What commercial catalog pricing uses before profit discounts.
    commercial_sale_value_per_token_usd: float = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)


class CommercialSettingsUpdate(BaseModel):
    token_value_usd: float = Field(gt=0, le=1000)
    operational_reserve_per_token_usd: float | None = Field(default=None, ge=0, le=1000)
    currency: str | None = Field(default="USD", min_length=3, max_length=3)




class BillingPolicyEntry(BaseModel):
    charge_infrastructure: bool
    apply_profit: bool


class ExecutionBillingPolicy(BaseModel):
    completed: BillingPolicyEntry
    cancelled: BillingPolicyEntry
    failed_workflow_or_user: BillingPolicyEntry
    failed_platform_or_provider: BillingPolicyEntry


class ExecutionBillingPolicyUpdate(ExecutionBillingPolicy):
    pass


class CommercialPricePreviewRequest(BaseModel):
    average_execution_cost_usd: float = Field(default=0, ge=0)
    desired_profit_percent: float = Field(default=0, ge=0, le=10000)
    desired_profit_usd: float | None = Field(default=None, ge=0, le=1000000)
    desired_profit_per_token_usd: float = Field(ge=0, le=1000000)


class CommercialPricePreviewResponse(BaseModel):
    average_execution_cost_usd: float
    desired_profit_percent: float
    desired_profit_usd: float = 0
    desired_profit_per_token_usd: float = 0
    token_value_usd: float
    currency: str
    final_price_usd: float
    required_tokens: int
    effective_margin_percent: float


class PricingRuleCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    operation_type: PricingOperationType = PricingOperationType.TRYON
    item_type: TryOnItemType = TryOnItemType.CLOTHING
    quality_mode: QualityMode = QualityMode.STANDARD
    generation_module_id: int | None = Field(default=None, ge=1)
    desired_profit_usd: float = Field(default=0, ge=0, le=1000000)
    desired_profit_per_token_usd: float = Field(ge=0, le=1000000)
    initial_estimated_duration_seconds: int = Field(default=30, ge=1, le=86400)
    technical_margin_seconds: int = Field(default=0, ge=0, le=3600)
    is_active: bool = True
    # Legacy inputs remain accepted during the BackOffice/AppWeb migration.
    average_execution_cost_usd: float | None = Field(default=None, ge=0)
    desired_profit_percent: float | None = Field(default=None, ge=0, le=10000)


class PricingRuleUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    generation_module_id: int | None = Field(default=None, ge=1)
    desired_profit_usd: float | None = Field(default=None, ge=0, le=1000000)
    desired_profit_per_token_usd: float | None = Field(default=None, ge=0, le=1000000)
    initial_estimated_duration_seconds: int | None = Field(default=None, ge=1, le=86400)
    technical_margin_seconds: int | None = Field(default=None, ge=0, le=3600)
    is_active: bool | None = None
    average_execution_cost_usd: float | None = Field(default=None, ge=0)
    desired_profit_percent: float | None = Field(default=None, ge=0, le=10000)


class PricingRuleResponse(BaseModel):
    id: int
    title: str
    operation_type: PricingOperationType
    item_type: TryOnItemType
    quality_mode: QualityMode
    generation_module_id: int | None
    desired_profit_usd: float
    desired_profit_per_token_usd: float
    initial_estimated_duration_seconds: int
    technical_margin_seconds: int
    # Legacy calculated fields retained so existing clients do not regress.
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
