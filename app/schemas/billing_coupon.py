from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.common.billing_enums import (
    CouponDiscountType,
    CouponDuration,
)


class BillingCouponCreate(BaseModel):
    code: str = Field(
        min_length=2,
        max_length=100,
        pattern=r"^[A-Za-z0-9_-]+$",
    )

    name: str = Field(min_length=2, max_length=255)
    description: str | None = None

    discount_type: CouponDiscountType
    duration: CouponDuration = CouponDuration.ONCE
    duration_in_months: int | None = Field(default=None, ge=1)

    percentage_off: Decimal | None = Field(
        default=None,
        gt=0,
        le=100,
    )

    amount_off: Decimal | None = Field(
        default=None,
        gt=0,
    )

    currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
    )

    max_redemptions: int | None = Field(default=None, ge=1)
    first_time_transaction_only: bool = False
    minimum_amount: Decimal | None = Field(default=None, ge=0)

    valid_from: datetime | None = None
    valid_until: datetime | None = None

    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_discount(self):
        self.code = self.code.upper()

        if self.currency:
            self.currency = self.currency.upper()

        if self.discount_type == CouponDiscountType.PERCENTAGE:
            if self.percentage_off is None:
                raise ValueError(
                    "percentage_off is required for percentage coupons."
                )

            if self.amount_off is not None:
                raise ValueError(
                    "amount_off must be empty for percentage coupons."
                )

        if self.discount_type == CouponDiscountType.FIXED_AMOUNT:
            if self.amount_off is None:
                raise ValueError(
                    "amount_off is required for fixed amount coupons."
                )

            if not self.currency:
                raise ValueError(
                    "currency is required for fixed amount coupons."
                )

            if self.percentage_off is not None:
                raise ValueError(
                    "percentage_off must be empty for fixed coupons."
                )

        if self.duration == CouponDuration.REPEATING:
            if self.duration_in_months is None:
                raise ValueError(
                    "duration_in_months is required for repeating coupons."
                )
        else:
            self.duration_in_months = None

        if (
            self.valid_from
            and self.valid_until
            and self.valid_until <= self.valid_from
        ):
            raise ValueError(
                "valid_until must be later than valid_from."
            )

        return self


class BillingCouponUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=255,
    )

    description: str | None = None
    max_redemptions: int | None = Field(default=None, ge=1)
    first_time_transaction_only: bool | None = None
    minimum_amount: Decimal | None = Field(default=None, ge=0)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    is_active: bool | None = None
    metadata: dict[str, Any] | None = None


class BillingCouponResponse(BaseModel):
    id: int
    code: str
    name: str
    description: str | None

    discount_type: CouponDiscountType
    duration: CouponDuration
    duration_in_months: int | None

    percentage_off: Decimal | None
    amount_off: Decimal | None
    currency: str | None

    stripe_coupon_id: str | None
    stripe_promotion_code_id: str | None
    stripe_configured: bool

    max_redemptions: int | None
    redemption_count: int

    first_time_transaction_only: bool
    minimum_amount: Decimal | None

    valid_from: datetime | None
    valid_until: datetime | None
    is_active: bool

    metadata: dict[str, Any]

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BillingCouponListResponse(BaseModel):
    items: list[BillingCouponResponse]
    total: int
    skip: int
    limit: int


class BillingCouponSyncResponse(BaseModel):
    coupon: BillingCouponResponse
    stripe_coupon_id: str
    stripe_promotion_code_id: str
    message: str


class BillingCouponValidationRequest(BaseModel):
    code: str = Field(min_length=2, max_length=100)
    purchase_amount: Decimal | None = Field(default=None, ge=0)


class BillingCouponValidationResponse(BaseModel):
    valid: bool
    coupon: BillingCouponResponse | None = None
    message: str