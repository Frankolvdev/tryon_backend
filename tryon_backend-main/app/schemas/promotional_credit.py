from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PromotionalCreditSettings(BaseModel):
    signup_enabled: bool = False
    signup_tokens: int = Field(default=0, ge=0, le=1000000)
    signup_provider: str = "general"
    allow_pending_settlement: bool = False


class PromotionalFundCreate(BaseModel):
    amount_usd: float = Field(gt=0)
    provider: str = Field(min_length=2, max_length=50)
    reference: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=1000)


class PromotionalFundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    provider: str
    original_usd: float
    remaining_usd: float
    reference: str | None = None
    description: str | None = None
    created_at: datetime


class PromotionalProviderBalance(BaseModel):
    provider: str
    funded_usd: float
    available_usd: float
    own_available_usd: float = 0.0
    recurring_available_usd: float = 0.0
    available_tokens: int


class PromotionalRecurringSourceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    provider: str = Field(min_length=2, max_length=50)
    recurring_amount_usd: float = Field(gt=0)
    current_available_usd: float = Field(ge=0)
    cycle_start: date
    recurrence: str = Field(default="monthly", pattern="^(weekly|monthly|quarterly|yearly)$")
    simulation_enabled: bool = False


class PromotionalRecurringSourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    recurring_amount_usd: float | None = Field(default=None, gt=0)
    recurrence: str | None = Field(default=None, pattern="^(weekly|monthly|quarterly|yearly)$")
    simulation_enabled: bool | None = None
    active: bool | None = None


class PromotionalFundingCycleResponse(BaseModel):
    id: int
    cycle_start: date
    cycle_end: date
    configured_amount_usd: float
    opening_available_usd: float
    current_available_usd: float
    expired_unused_usd: float
    returned_after_close_usd: float
    status: str


class PromotionalRecurringSourceResponse(BaseModel):
    id: int
    name: str
    provider: str
    source_type: str
    recurrence: str
    recurring_amount_usd: float
    current_cycle_start: date
    current_cycle_end: date
    current_available_usd: float
    active: bool
    simulation_enabled: bool = False
    cycles: list[PromotionalFundingCycleResponse] = Field(default_factory=list)


class PromotionalCycleWebhookRequest(BaseModel):
    simulation: bool = False


class PromotionalCycleWebhookResult(BaseModel):
    source_id: int
    source_name: str
    simulation: bool
    effective_date: date
    changed_cycles: int
    would_roll_cycles: int
    current_cycle_start: date
    current_cycle_end: date
    projected_cycle_start: date
    projected_cycle_end: date
    projected_opening_usd: float | None = None
    message: str


class PromotionalGrantCreate(BaseModel):
    user_id: int | None = None
    user_email: str | None = None
    tokens: int = Field(gt=0, le=1000000)
    provider: str = Field(min_length=2, max_length=50)

    @model_validator(mode="after")
    def validate_user(self):
        if self.user_id is None and not str(self.user_email or "").strip():
            raise ValueError("user_id or user_email is required")
        return self


class PromotionalGrantResult(BaseModel):
    requested_tokens: int
    granted_tokens: int
    provider: str
    amount_reserved_usd: float
    user_balance: int | None = None
    grant_ids: list[int] = Field(default_factory=list)


class PromotionalRevokeCreate(BaseModel):
    user_id: int
    tokens: int = Field(gt=0, le=1000000)
    reason: str | None = Field(default=None, max_length=500)


class PromotionalRevokeResult(BaseModel):
    requested_tokens: int
    revoked_tokens: int
    amount_returned_usd: float
    user_balance: int
    affected_lot_ids: list[int] = Field(default_factory=list)


class PromotionalGrantHistory(BaseModel):
    id: int
    fund_id: int
    lot_id: int
    user_id: int
    user_email: str | None = None
    tokens_granted: int
    reserve_per_token_usd: float
    amount_reserved_usd: float
    grant_type: str
    created_at: datetime


class PromotionalCreditSummary(BaseModel):
    reserve_per_token_usd: float
    generation_infrastructure_reserve_per_token_usd: float
    total_funded_usd: float
    total_available_usd: float
    total_own_available_usd: float = 0.0
    total_recurring_available_usd: float = 0.0
    provider_balances: list[PromotionalProviderBalance] = Field(default_factory=list)
    settings: PromotionalCreditSettings
    funds: list[PromotionalFundResponse] = Field(default_factory=list)
    grants: list[PromotionalGrantHistory] = Field(default_factory=list)
    recurring_sources: list[PromotionalRecurringSourceResponse] = Field(default_factory=list)
