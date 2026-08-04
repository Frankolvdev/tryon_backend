from datetime import datetime
from decimal import Decimal
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False, index=True)
