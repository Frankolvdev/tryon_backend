from datetime import datetime
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
    available_tokens: int


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
    provider_balances: list[PromotionalProviderBalance] = Field(default_factory=list)
    settings: PromotionalCreditSettings
    funds: list[PromotionalFundResponse] = Field(default_factory=list)
    grants: list[PromotionalGrantHistory] = Field(default_factory=list)
