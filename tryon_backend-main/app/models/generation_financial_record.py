from datetime import datetime
from decimal import Decimal
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.common.time import utc_now
from app.db.database import Base

class GenerationFinancialRecord(Base):
    __tablename__ = 'generation_financial_records'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    execution_id: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False)
    generation_module_id: Mapped[int | None] = mapped_column(ForeignKey('generation_modules.id', ondelete='SET NULL'), index=True)
    module_key: Mapped[str] = mapped_column(String(150), index=True, nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), index=True)
    status: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    tokens_consumed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recognized_revenue_usd: Mapped[Decimal] = mapped_column(Numeric(14,6), default=0, nullable=False)
    infrastructure_cost_usd: Mapped[Decimal] = mapped_column(Numeric(14,6), default=0, nullable=False)
    gross_profit_usd: Mapped[Decimal] = mapped_column(Numeric(14,6), default=0, nullable=False)
    gross_margin_percent: Mapped[Decimal | None] = mapped_column(Numeric(9,4))
    traceability_status: Mapped[str] = mapped_column(String(30), default='exact', nullable=False, index=True)
    breakdown_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
