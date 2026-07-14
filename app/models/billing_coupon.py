from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.billing_enums import CouponDiscountType, CouponDuration
from app.common.time import utc_now
from app.db.database import Base


class BillingCoupon(Base):
    __tablename__ = "billing_coupons"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    code: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    discount_type: Mapped[str] = mapped_column(
        String(50),
        default=CouponDiscountType.PERCENTAGE.value,
        nullable=False,
        index=True,
    )

    duration: Mapped[str] = mapped_column(
        String(30),
        default=CouponDuration.ONCE.value,
        nullable=False,
    )

    duration_in_months: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    percentage_off: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )

    amount_off: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    currency: Mapped[str | None] = mapped_column(
        String(3),
        nullable=True,
    )

    stripe_coupon_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
        index=True,
    )

    stripe_promotion_code_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
        index=True,
    )

    max_redemptions: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    redemption_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    first_time_transaction_only: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    minimum_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    valid_from: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )

    metadata_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )