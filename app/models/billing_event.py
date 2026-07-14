from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.common.billing_enums import (
    BillingEventStatus,
    BillingProvider,
)
from app.common.time import utc_now
from app.db.database import Base


class BillingEvent(Base):
    __tablename__ = "billing_events"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_event_id",
            name="uq_billing_event_provider_event",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    provider: Mapped[str] = mapped_column(
        String(50),
        default=BillingProvider.STRIPE.value,
        nullable=False,
        index=True,
    )

    provider_event_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    event_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default=BillingEventStatus.RECEIVED.value,
        nullable=False,
        index=True,
    )

    payload_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    result_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    processing_attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    received_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
        index=True,
    )

    processed_at: Mapped[datetime | None] = mapped_column(
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