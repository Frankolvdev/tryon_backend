from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class PricingSimulatorScenarioRequest(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    discount_percent: float = Field(default=0, ge=0, le=100)


class PricingSimulatorRequest(BaseModel):
    generation_module_id: int = Field(ge=1)
    token_value_usd: float | None = Field(default=None, gt=0, le=1000)
    desired_profit_per_token_usd: float | None = Field(default=None, ge=0, le=1000)
    duration_mode: str = Field(default="historical", pattern="^(historical|initial|manual)$")
    manual_duration_seconds: float | None = Field(default=None, gt=0, le=86400)
    scenarios: list[PricingSimulatorScenarioRequest] = Field(default_factory=list, max_length=12)
    target_profit_usd: float | None = Field(default=None, ge=0, le=1000000)
    target_tokens_min: int | None = Field(default=None, ge=1, le=1000000)
    target_tokens_max: int | None = Field(default=None, ge=1, le=1000000)
    worst_discount_percent: float = Field(default=0, ge=0, le=100)

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.duration_mode == "manual" and self.manual_duration_seconds is None:
            raise ValueError("manual_duration_seconds is required when duration_mode is manual")
        if self.target_tokens_min and self.target_tokens_max and self.target_tokens_min > self.target_tokens_max:
            raise ValueError("target_tokens_min cannot exceed target_tokens_max")
        return self


class PricingSimulatorScenarioResponse(BaseModel):
    label: str
    discount_percent: float
    tokens: int
    customer_value_usd: float
    infrastructure_cost_usd: float
    operational_reserve_usd: float = 0
    normal_profit_usd: float
    discount_given_usd: float
    profit_after_discount_usd: float
    rounding_surplus_usd: float
    company_total_usd: float


class PricingSimulatorRecommendation(BaseModel):
    token_value_usd: float
    desired_profit_per_token_usd: float
    tokens: int
    worst_discount_percent: float
    estimated_company_profit_usd: float
    estimated_customer_value_usd: float
    distance_from_target_usd: float


class PricingSimulatorResponse(BaseModel):
    generation_module_id: int
    module_key: str
    module_name: str
    pricing_rule_id: int
    pricing_rule_title: str
    provider: str
    gpu_key: str | None
    gpu_cost_usd_per_second: float
    duration_seconds: float
    duration_source: str
    historical_samples_used: int
    estimate_confidence: str
    scaledown_seconds: int
    technical_margin_seconds: int
    billable_seconds: float
    infrastructure_cost_usd: float
    current_token_value_usd: float
    current_operational_reserve_per_token_usd: float = 0
    current_profit_per_token_usd: float
    simulated_token_value_usd: float
    simulated_operational_reserve_per_token_usd: float = 0
    simulated_profit_per_token_usd: float
    scenarios: list[PricingSimulatorScenarioResponse]
    recommendations: list[PricingSimulatorRecommendation]
    warnings: list[str]
