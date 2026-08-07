from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.common.time import utc_now
from app.db.database import Base


class PromotionalCreditFund(Base):
    __tablename__ = "promotional_credit_funds"
    __table_args__ = (
        CheckConstraint("original_usd > 0", name="ck_promo_fund_original_positive"),
        CheckConstraint("remaining_usd >= 0", name="ck_promo_fund_remaining_nonnegative"),
        CheckConstraint("remaining_usd <= original_usd", name="ck_promo_fund_remaining_le_original"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    original_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    remaining_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False, index=True)


class PromotionalTokenGrant(Base):
    __tablename__ = "promotional_token_grants"
    __table_args__ = (
        CheckConstraint("tokens_granted > 0", name="ck_promo_grant_tokens_positive"),
        CheckConstraint("reserve_per_token_usd > 0", name="ck_promo_grant_reserve_positive"),
        CheckConstraint("amount_reserved_usd > 0", name="ck_promo_grant_amount_positive"),
        UniqueConstraint("lot_id", name="uq_promo_grant_lot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fund_id: Mapped[int] = mapped_column(
        ForeignKey("promotional_credit_funds.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    lot_id: Mapped[int] = mapped_column(
        ForeignKey("token_value_lots.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tokens_granted: Mapped[int] = mapped_column(Integer, nullable=False)
    reserve_per_token_usd: Mapped[Decimal] = mapped_column(Numeric(14, 9), nullable=False)
    amount_reserved_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    grant_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False, index=True)


class PromotionalCreditReturn(Base):
    __tablename__ = "promotional_credit_returns"
    __table_args__ = (
        CheckConstraint("amount_usd > 0", name="ck_promo_return_amount_positive"),
        UniqueConstraint("grant_id", "reason", "reference_id", name="uq_promo_return_idempotency"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fund_id: Mapped[int] = mapped_column(
        ForeignKey("promotional_credit_funds.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    grant_id: Mapped[int] = mapped_column(
        ForeignKey("promotional_token_grants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    reason: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    reference_id: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False, index=True)
