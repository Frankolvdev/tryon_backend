from datetime import datetime
from decimal import Decimal
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from app.common.time import utc_now
from app.db.database import Base

class TokenConsumptionAllocation(Base):
    __tablename__ = 'token_consumption_allocations'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    execution_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    lot_id: Mapped[int] = mapped_column(ForeignKey('token_value_lots.id', ondelete='RESTRICT'), index=True, nullable=False)
    token_transaction_id: Mapped[int | None] = mapped_column(ForeignKey('token_transactions.id', ondelete='SET NULL'), index=True)
    tokens_allocated: Mapped[int] = mapped_column(Integer, nullable=False)
    tokens_reversed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    effective_token_value_usd: Mapped[Decimal] = mapped_column(Numeric(14,9), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
