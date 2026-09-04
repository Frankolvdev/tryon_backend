from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class InfrastructureProviderBalanceResponse(BaseModel):
    provider: str
    funded_usd: float
    infrastructure_cost_usd: float
    credit_available_usd: float
    unfunded_cost_usd: float
    released_credit_usd: float


class CashboxSummaryResponse(BaseModel):
    collected_usd: float
    available_usd: float
    protected_infrastructure_usd: float
    blocked_profit_usd: float
    released_commercial_profit_usd: float
    rounding_and_operational_surplus_usd: float
    profitability_surplus_usd: float = 0.0
    expiration_releases_usd: float
    withdrawals_usd: float
    infrastructure_cash_available_usd: float = 0.0
    infrastructure_funded_usd: float = 0.0
    provider_credit_available_usd: float = 0.0
    provider_cost_unfunded_usd: float = 0.0
    provider_credit_released_usd: float = 0.0
    provider_balances: list[InfrastructureProviderBalanceResponse] = Field(default_factory=list)
    pending_recovery_generations: int = 0
    pending_recovery_tokens: int = 0
    pending_recovery_infrastructure_usd: float = 0.0
    pending_recovery_profit_estimated_usd: float = 0.0
    pending_recovery_economic_estimated_usd: float = 0.0
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
    operational_reserve_per_token_usd: float = 0.0
    operational_reserve_total_usd: float = 0.0
    operational_reserve_released_usd: float = 0.0
    commercial_profit_total_usd: float
    commercial_profit_released_usd: float
    realized_extra_profit_usd: float
    profitability_surplus_usd: float = 0.0
    profitability_surplus_total_usd: float = 0.0
    provider_profitability_credit_usd: float = 0.0
    total_available_from_bag_usd: float
    protected_infrastructure_remaining_usd: float
    infrastructure_used_usd: float
    infrastructure_funded_usd: float = 0.0
    infrastructure_unfunded_usd: float = 0.0
    provider_credit_released_usd: float = 0.0
    rounding_surplus_usd: float
    rounding_surplus_total_usd: float = 0.0
    provider_rounding_credit_usd: float = 0.0
    expiration_release_usd: float
    coupon_code: str | None = None
    plan_name: str | None = None
    package_name: str | None = None
    benefit_source: str | None = None
    benefit_label: str | None = None
    profit_discount_percent: float = 0.0
    snapshot_version: int | None = None
    snapshot_source: str | None = None
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
    profitability_surplus_usd: float = 0.0
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
    simulation_enabled: bool = False


class TokenBagExpirationSimulationRequest(BaseModel):
    confirm: bool = False


class TokenBagExpirationSimulationResponse(BaseModel):
    bag_id: int
    previous_status: str
    current_status: str
    expired_tokens: int
    commercial_profit_released_usd: float
    infrastructure_reserve_released_usd: float
    infrastructure_cash_released_usd: float = 0.0
    provider_credit_released_usd: float = 0.0
    provider_credit_released_by_provider: dict[str, float] = Field(default_factory=dict)
    promotional_credit_returned_usd: float = 0.0
    total_available_from_bag_usd: float
    expires_at: datetime | None
    expired_at: datetime


class ExpirationSettingsUpdate(BaseModel):
    enabled: bool = True
    days: int = Field(default=730, ge=1, le=3650)


class InfrastructureFundingCreate(BaseModel):
    amount_usd: float = Field(gt=0)
    provider: str = Field(min_length=2, max_length=50)
    beneficiary: str | None = None
    concept: str = Field(min_length=2, max_length=255)
    method: str | None = None
    proof_url: str | None = None
    notes: str | None = None
    funded_at: datetime | None = None


class InfrastructureFundingAllocationResponse(BaseModel):
    id: int
    lot_id: int
    amount_usd: float


class InfrastructureFundingResponse(BaseModel):
    id: int
    amount_usd: float
    currency: str
    provider: str
    beneficiary: str | None
    concept: str
    method: str | None
    proof_url: str | None
    notes: str | None
    created_by_user_id: int | None
    funded_at: datetime
    created_at: datetime
    allocations: list[InfrastructureFundingAllocationResponse] = Field(default_factory=list)

class PendingRecoveryItemResponse(BaseModel):
    execution_id: str
    module_key: str
    user_id: int | None = None
    user_email: str | None = None
    provider: str | None = None
    status: str
    billing_access_status: str
    tokens_charged: int
    pending_tokens: int
    estimated_final_tokens: int
    infrastructure_cost_usd: float
    infrastructure_covered_usd: float
    infrastructure_pending_usd: float
    profit_realized_usd: float
    profit_pending_estimated_usd: float
    economic_pending_estimated_usd: float
    created_at: datetime


class PendingRecoverySummaryResponse(BaseModel):
    pending_generations: int
    pending_tokens: int
    infrastructure_pending_usd: float
    profit_pending_estimated_usd: float
    economic_pending_estimated_usd: float


class PendingRecoveryListResponse(BaseModel):
    items: list[PendingRecoveryItemResponse] = Field(default_factory=list)
    summary: PendingRecoverySummaryResponse


class OperationalCashboxSummaryResponse(BaseModel):
    operational_reserve_per_token_usd: float
    commercial_sale_value_per_token_usd: float
    lifetime_operational_funds_usd: float
    released_operational_funds_usd: float
    blocked_operational_funds_usd: float
    spent_operational_funds_usd: float
    available_operational_funds_usd: float
    contributing_bags: int


class OperationalExpenseCreate(BaseModel):
    amount_usd: float = Field(gt=0)
    category: str = Field(min_length=2, max_length=80)
    beneficiary: str | None = None
    concept: str = Field(min_length=2, max_length=255)
    method: str | None = None
    proof_url: str | None = None
    notes: str | None = None
    spent_at: datetime | None = None


class OperationalExpenseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    amount_usd: float
    currency: str
    category: str
    beneficiary: str | None
    concept: str
    method: str | None
    proof_url: str | None
    notes: str | None
    created_by_user_id: int | None
    spent_at: datetime
    created_at: datetime
