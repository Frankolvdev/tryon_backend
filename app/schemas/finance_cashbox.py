from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class CashboxSummaryResponse(BaseModel):
    collected_usd: float
    available_usd: float
    protected_infrastructure_usd: float
    blocked_profit_usd: float
    released_commercial_profit_usd: float
    rounding_and_operational_surplus_usd: float
    expiration_releases_usd: float
    withdrawals_usd: float
    active_bags: int
    new_bags: int
    expired_bags: int

class WithdrawalCreate(BaseModel):
    amount_usd: float = Field(gt=0)
    beneficiary: str | None = None
    concept: str = Field(min_length=2, max_length=255)
    method: str | None = None
    proof_url: str | None = None
    notes: str | None = None
    withdrawn_at: datetime | None = None

class WithdrawalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    amount_usd: float
    currency: str
    beneficiary: str | None
    concept: str
    method: str | None
    proof_url: str | None
    notes: str | None
    created_by_user_id: int | None
    withdrawn_at: datetime
    created_at: datetime

class TokenBagResponse(BaseModel):
    id: int
    user_id: int
    user_email: str | None = None
    source: str
    source_label: str
    reference_id: str | None
    status: str
    original_tokens: int
    remaining_tokens: int
    consumed_tokens: int
    amount_paid_usd: float
    effective_token_value_usd: float
    normal_profit_per_token_usd: float
    effective_profit_per_token_usd: float
    infrastructure_capacity_per_token_usd: float
    commercial_profit_total_usd: float
    commercial_profit_released_usd: float
    protected_infrastructure_remaining_usd: float
    infrastructure_used_usd: float
    rounding_surplus_usd: float
    expiration_release_usd: float
    coupon_code: str | None = None
    plan_name: str | None = None
    payment_status: str | None = None
    refundable: bool
    refund_reason: str
    activated_at: datetime | None
    expires_at: datetime | None
    expired_at: datetime | None
    created_at: datetime

class TokenBagListResponse(BaseModel):
    items: list[TokenBagResponse]
    total: int

class TokenBagGenerationResponse(BaseModel):
    execution_id: str
    tokens_used: int
    created_at: datetime
    infrastructure_cost_usd: float
    company_profit_usd: float
    rounding_surplus_usd: float
    status: str | None = None

class TokenBagDetailResponse(BaseModel):
    bag: TokenBagResponse
    generations: list[TokenBagGenerationResponse]
    timeline: list[dict]
    purchase_id: int | None = None

class ExpirationSettingsResponse(BaseModel):
    enabled: bool
    days: int

class ExpirationSettingsUpdate(BaseModel):
    enabled: bool = True
    days: int = Field(default=730, ge=1, le=3650)
