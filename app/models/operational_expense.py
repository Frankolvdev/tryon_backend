from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.time import utc_now
from app.db.database import Base


class OperationalExpense(Base):
    __tablename__ = "operational_expenses"
    __table_args__ = (
        CheckConstraint("amount_usd > 0", name="ck_operational_expense_amount_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    beneficiary: Mapped[str | None] = mapped_column(String(255))
    concept: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str | None] = mapped_column(String(100))
    proof_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    spent_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
