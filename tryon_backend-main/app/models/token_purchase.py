from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.billing_enums import TokenPurchaseStatus
from app.common.time import utc_now
from app.db.database import Base


class TokenPurchase(Base):
    __tablename__ = "token_purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    token_package_id: Mapped[int | None] = mapped_column(
        ForeignKey("token_packages.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    billing_payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("billing_payments.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default=TokenPurchaseStatus.PENDING.value,
        nullable=False,
        index=True,
    )

    tokens_amount: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    bonus_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    provider_checkout_session_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
        index=True,
    )

    provider_payment_intent_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    token_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("token_transactions.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )

    metadata_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    credited_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    refunded_at: Mapped[datetime | None] = mapped_column(
        DateTime,
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