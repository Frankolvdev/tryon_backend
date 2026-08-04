from pydantic import BaseModel


class FinancialProtectionRuleDiagnostic(BaseModel):
    pricing_rule_id: int
    generation_module_id: int
    module_key: str
    module_name: str
    desired_profit_usd: float
    is_limiting: bool = False


class FinancialProtectionReport(BaseModel):
    safe_profit_usd: float | None = None
    maximum_allowed_discount_percent: float = 100.0
    highest_active_discount_percent: float = 0.0
    available_discount_percentage_points: float = 100.0
    status: str
    limiting_pricing_rule_id: int | None = None
    limiting_generation_module_id: int | None = None
    limiting_module_key: str | None = None
    limiting_module_name: str | None = None
    diagnostics: list[FinancialProtectionRuleDiagnostic] = []
    warnings: list[str] = []


class ProtectedCommercialPrice(BaseModel):
    nominal_price_usd: float
    requested_discount_percent: float
    effective_discount_percent: float
    maximum_allowed_discount_percent: float
    safe_profit_usd: float
    discounted_profit_usd: float
    remaining_profit_usd: float
    discount_amount_usd: float
    final_price_usd: float
    potential_loss_usd: float = 0.0
    limiting_pricing_rule_id: int | None = None
    limiting_generation_module_id: int | None = None
    limiting_module_name: str | None = None
    # Legacy response field kept so existing clients do not break.
    protected_discount_percent: float = 100.0
    calculated_maximum_safe_discount_percent: float = 100.0
    protection_limited: bool = False
