from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import TokenTransactionType
from app.common.time import utc_now
from app.db.database import Base


class TokenTransaction(Base):
    __tablename__ = "token_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    transaction_type: Mapped[str] = mapped_column(
        String(50),
        default=TokenTransactionType.CREDIT.value,
        nullable=False,
        index=True,
    )

    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)

    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)