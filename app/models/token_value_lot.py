from datetime import datetime
from decimal import Decimal
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.common.time import utc_now
from app.db.database import Base

class TokenValueLot(Base):
    __tablename__ = 'token_value_lots'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String(255), index=True)
    original_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    remaining_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_paid_usd: Mapped[Decimal] = mapped_column(Numeric(14,6), default=0, nullable=False)
    effective_token_value_usd: Mapped[Decimal] = mapped_column(Numeric(14,9), default=0, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default='new', nullable=False, index=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    commercial_profit_released: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    released_commercial_profit_usd: Mapped[Decimal] = mapped_column(Numeric(14,6), default=0, nullable=False)
    released_expiration_usd: Mapped[Decimal] = mapped_column(Numeric(14,6), default=0, nullable=False)
    operational_reserve_released: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    released_operational_reserve_usd: Mapped[Decimal] = mapped_column(Numeric(14,6), default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False, index=True)
