from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.common.time import utc_now
from app.db.database import Base


class PromotionalFundingSource(Base):
    """Optional policy layer on top of the existing promotional fund ledger.

    Existing PromotionalCreditFund rows remain company-owned/manual funding.
    A recurring provider source creates one ordinary PromotionalCreditFund per
    billing cycle, so grants and token lots keep using the exact same ledger.
    """

    __tablename__ = "promotional_funding_sources"
    __table_args__ = (
        CheckConstraint("recurring_amount_usd > 0", name="ck_promo_source_recurring_positive"),
        CheckConstraint("current_cycle_end > current_cycle_start", name="ck_promo_source_cycle_dates"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, default="recurring_provider", index=True)
    recurrence: Mapped[str] = mapped_column(String(30), nullable=False, default="monthly")
    recurring_amount_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    current_cycle_start: Mapped[date] = mapped_column(Date, nullable=False)
    current_cycle_end: Mapped[date] = mapped_column(Date, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class PromotionalFundingCycle(Base):
    __tablename__ = "promotional_funding_cycles"
    __table_args__ = (
        CheckConstraint("cycle_end > cycle_start", name="ck_promo_cycle_dates"),
        CheckConstraint("configured_amount_usd > 0", name="ck_promo_cycle_configured_positive"),
        CheckConstraint("opening_available_usd >= 0", name="ck_promo_cycle_opening_nonnegative"),
        CheckConstraint("expired_unused_usd >= 0", name="ck_promo_cycle_expired_nonnegative"),
        CheckConstraint("returned_after_close_usd >= 0", name="ck_promo_cycle_returned_closed_nonnegative"),
        UniqueConstraint("source_id", "cycle_start", "cycle_end", name="uq_promo_source_cycle_window"),
        UniqueConstraint("fund_id", name="uq_promo_cycle_fund"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("promotional_funding_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fund_id: Mapped[int | None] = mapped_column(
        ForeignKey("promotional_credit_funds.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    cycle_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    cycle_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    configured_amount_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    opening_available_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    expired_unused_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False, default=Decimal("0"))
    returned_after_close_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False, default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
