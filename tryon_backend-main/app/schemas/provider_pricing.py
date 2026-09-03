from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProviderGpuPriceUpsert(BaseModel):
    provider: str = Field(min_length=2, max_length=50)
    gpu_key: str = Field(min_length=1, max_length=100)
    cost_usd_per_second: float = Field(ge=0, le=1000)
    is_active: bool = True


class ProviderGpuPriceResponse(ProviderGpuPriceUpsert):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AppliedPricingRuleResponse(BaseModel):
    rule_id: int
    rule_title: str
    generation_module_id: int
    module_key: str
    module_name: str
    provider: str
    gpu_key: str | None
    gpu_cost_usd_per_second: float | None
    estimated_duration_seconds: float
    estimate_source: str
    historical_samples_used: int = 0
    estimate_confidence: str = "low"
    estimate_updated_at: str | None = None
    scaledown_seconds: int
    technical_margin_seconds: int
    estimated_billable_seconds: float
    estimated_infrastructure_cost_usd: float | None
    desired_profit_usd: float
    desired_profit_per_token_usd: float = 0
    estimated_final_price_usd: float | None
    token_value_usd: float
    estimated_tokens: int | None
    configured: bool
    warnings: list[str] = []
