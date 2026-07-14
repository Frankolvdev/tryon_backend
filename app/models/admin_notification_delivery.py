from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.time import utc_now
from app.db.database import Base


class AdminNotificationDelivery(Base):
    __tablename__ = "admin_notification_deliveries"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    notification_id: Mapped[int] = mapped_column(
        ForeignKey(
            "admin_notifications.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    channel_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "admin_notification_channels.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    recipient_user_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    channel_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    destination: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        nullable=False,
        index=True,
    )

    attempt_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    max_attempts: Mapped[int] = mapped_column(
        Integer,
        default=5,
        nullable=False,
    )

    provider_message_id: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        index=True,
    )

    provider_status_code: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    error_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    provider_response_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )

    processing_started_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime,
        nullable=True,
    )

    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )

    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
        index=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    __table_args__ = (
        Index(
            "ix_admin_notification_delivery_queue",
            "status",
            "next_retry_at",
            "scheduled_at",
        ),
        Index(
            "ix_admin_notification_delivery_notification",
            "notification_id",
            "channel_type",
            "status",
        ),
        Index(
            "ix_admin_notification_delivery_recipient",
            "recipient_user_id",
            "status",
            "created_at",
        ),
    )