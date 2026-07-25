from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.time import utc_now
from app.db.database import Base


class AdminNotificationChannel(Base):
    __tablename__ = "admin_notification_channels"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    channel_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="active",
        nullable=False,
        index=True,
    )

    destination: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
    )

    display_name: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    integration_provider: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    configuration_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    minimum_priority: Mapped[str] = mapped_column(
        String(30),
        default="normal",
        nullable=False,
        index=True,
    )

    send_success_notifications: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    send_info_notifications: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    send_warning_notifications: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    send_error_notifications: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    send_critical_notifications: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    last_tested_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    last_test_success: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
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
        UniqueConstraint(
            "user_id",
            "channel_type",
            name=(
                "uq_admin_notification_channel_user_type"
            ),
        ),
        Index(
            "ix_admin_notification_channels_delivery",
            "channel_type",
            "is_enabled",
            "status",
        ),
    )