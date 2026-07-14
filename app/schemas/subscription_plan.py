from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.common.billing_enums import BillingInterval


class SubscriptionPlanCreate(BaseModel):
    key: str = Field(
        min_length=2,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9_-]*$",
    )

    name: str = Field(min_length=2, max_length=255)
    description: str | None = None

    billing_interval: BillingInterval = BillingInterval.MONTH

    currency: str = Field(
        default="USD",
        min_length=3,
        max_length=3,
    )

    price_amount: Decimal = Field(ge=0)

    tokens_per_period: int = Field(default=0, ge=0)
    max_generations_per_period: int | None = Field(default=None, ge=1)
    priority: int = Field(default=10, ge=0, le=1000)

    features: list[str] = []
    metadata: dict[str, Any] = {}

    is_public: bool = True
    is_active: bool = True
    sort_order: int = Field(default=0, ge=0)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("features")
    @classmethod
    def normalize_features(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []

        for value in values:
            clean_value = value.strip()

            if clean_value and clean_value not in normalized:
                normalized.append(clean_value)

        return normalized


class SubscriptionPlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None

    billing_interval: BillingInterval | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    price_amount: Decimal | None = Field(default=None, ge=0)

    tokens_per_period: int | None = Field(default=None, ge=0)
    max_generations_per_period: int | None = Field(default=None, ge=1)
    priority: int | None = Field(default=None, ge=0, le=1000)

    features: list[str] | None = None
    metadata: dict[str, Any] | None = None

    is_public: bool | None = None
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value

    @field_validator("features")
    @classmethod
    def normalize_features(
        cls,
        values: list[str] | None,
    ) -> list[str] | None:
        if values is None:
            return None

        normalized: list[str] = []

        for value in values:
            clean_value = value.strip()

            if clean_value and clean_value not in normalized:
                normalized.append(clean_value)

        return normalized


class SubscriptionPlanResponse(BaseModel):
    id: int

    key: str
    name: str
    description: str | None

    billing_interval: BillingInterval
    currency: str
    price_amount: Decimal

    tokens_per_period: int
    max_generations_per_period: int | None
    priority: int

    stripe_product_id: str | None
    stripe_price_id: str | None

    stripe_configured: bool

    features: list[str]
    metadata: dict[str, Any]

    is_public: bool
    is_active: bool
    sort_order: int

    created_at: object
    updated_at: object

    model_config = ConfigDict(from_attributes=True)


class SubscriptionPlanListResponse(BaseModel):
    items: list[SubscriptionPlanResponse]
    total: int
    skip: int
    limit: int


class SubscriptionPlanSyncResponse(BaseModel):
    plan: SubscriptionPlanResponse
    stripe_product_id: str
    stripe_price_id: str
    price_replaced: bool
    message: str


class SubscriptionPlanSeedResponse(BaseModel):
    created: int
    skipped: int
    total: int