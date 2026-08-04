from pydantic import BaseModel, Field


class FinancialProtectionSettings(BaseModel):
    protected_discount_percent: float = Field(default=0, ge=0, le=100)
    duration_safety_buffer_percent: float = Field(default=10, ge=0, le=200)


class FinancialProtectionSettingsUpdate(FinancialProtectionSettings):
    pass


class FinancialProtectionRuleDiagnostic(BaseModel):
    pricing_rule_id: int
    generation_module_id: int
    module_key: str
    module_name: str
    provider: str
    gpu_key: str | None = None
    protected_duration_seconds: float
    billable_seconds: float
    gpu_cost_usd_per_second: float | None = None
    infrastructure_cost_usd: float | None = None
    desired_profit_usd: float
    normal_price_usd: float | None = None
    maximum_safe_discount_percent: float | None = None
    configured: bool
    warnings: list[str] = []


class FinancialProtectionReport(BaseModel):
    protected_discount_percent: float
    duration_safety_buffer_percent: float
    calculated_maximum_safe_discount_percent: float | None = None
    available_headroom_percentage_points: float | None = None
    status: str
    limiting_pricing_rule_id: int | None = None
    limiting_generation_module_id: int | None = None
    limiting_module_key: str | None = None
    limiting_module_name: str | None = None
    limiting_provider: str | None = None
    limiting_gpu_key: str | None = None
    diagnostics: list[FinancialProtectionRuleDiagnostic] = []
    warnings: list[str] = []


class ProtectedCommercialPrice(BaseModel):
    nominal_price_usd: float
    requested_discount_percent: float
    effective_discount_percent: float
    discount_amount_usd: float
    final_price_usd: float
    protected_discount_percent: float
    calculated_maximum_safe_discount_percent: float | None = None
    protection_limited: bool
