import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.common.enums import TokenTransactionType


def _commercial_description(value: str | None) -> str | None:
    if not value:
        return value

    if re.match(
        r"^Subscription tokens for plan\s+[^;]+(?:;\s*invoice\s+\S+)?$",
        value,
        flags=re.IGNORECASE,
    ):
        return "Tokens incluidos en tu suscripción"

    if re.match(
        r"^Token purchase #\d+$",
        value,
        flags=re.IGNORECASE,
    ):
        return "Tokens acreditados por compra"

    return re.sub(
        r";\s*invoice\s+in_[A-Za-z0-9_]+",
        "",
        value,
        flags=re.IGNORECASE,
    ).strip()


class TokenPackageCreate(BaseModel):
    name: str
    description: str | None = None
    tokens_amount: int = Field(gt=0)
    price_cents: int | None = Field(default=None, gt=0)
    currency: str = "usd"
    stripe_price_id: str | None = None
    is_active: bool = True


class TokenPackageUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    tokens_amount: int | None = Field(default=None, gt=0)
    price_cents: int | None = Field(default=None, gt=0)
    currency: str | None = None
    stripe_price_id: str | None = None
    is_active: bool | None = None


class TokenPackageResponse(BaseModel):
    id: int
    name: str
    description: str | None
    tokens_amount: int
    price_cents: int
    calculated_price_cents: int
    commercial_token_value: float
    price_is_automatic: bool = True
    currency: str
    stripe_price_id: str | None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenTransactionResponse(BaseModel):
    id: int
    user_id: int
    transaction_type: TokenTransactionType
    amount: int
    balance_after: int
    source: str | None
    reference_id: str | None
    description: str | None
    created_at: datetime

    @field_validator("description", mode="before")
    @classmethod
    def sanitize_description(cls, value: str | None) -> str | None:
        return _commercial_description(value)

    model_config = ConfigDict(from_attributes=True)


class TokenBalanceResponse(BaseModel):
    token_balance: int


class TokenConsumeRequest(BaseModel):
    amount: int = Field(gt=0)
    source: str = "tryon"
    reference_id: str | None = None
    description: str | None = None


class AdminTokenAdjustRequest(BaseModel):
    user_id: int
    amount: int
    description: str | None = None
