from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.common.time import utc_now
from app.db.database import Base


class InfrastructureFundingMovement(Base):
    __tablename__ = "infrastructure_funding_movements"
    __table_args__ = (
        CheckConstraint("amount_usd > 0", name="ck_infra_funding_amount_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    beneficiary: Mapped[str | None] = mapped_column(String(255))
    concept: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str | None] = mapped_column(String(100))
    proof_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    funded_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )


class InfrastructureFundingAllocation(Base):
    __tablename__ = "infrastructure_funding_allocations"
    __table_args__ = (
        CheckConstraint("amount_usd > 0", name="ck_infra_funding_allocation_positive"),
        UniqueConstraint("movement_id", "lot_id", name="uq_infra_funding_movement_lot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    movement_id: Mapped[int] = mapped_column(
        ForeignKey("infrastructure_funding_movements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lot_id: Mapped[int] = mapped_column(
        ForeignKey("token_value_lots.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )


class InfrastructureProviderCreditRelease(Base):
    __tablename__ = "infrastructure_provider_credit_releases"
    __table_args__ = (
        CheckConstraint("amount_usd > 0", name="ck_infra_credit_release_positive"),
        UniqueConstraint("funding_allocation_id", name="uq_infra_credit_release_allocation"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lot_id: Mapped[int] = mapped_column(
        ForeignKey("token_value_lots.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    funding_allocation_id: Mapped[int] = mapped_column(
        ForeignKey("infrastructure_funding_allocations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    reason: Mapped[str] = mapped_column(
        String(80), default="token_bag_expiration", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False, index=True
    )
