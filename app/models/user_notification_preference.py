from datetime import datetime, time

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.time import utc_now
from app.db.database import Base


class UserNotificationPreference(Base):
    __tablename__ = "user_notification_preferences"

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
        unique=True,
        index=True,
    )

    in_app_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    email_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    web_push_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    marketing_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    tryon_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    billing_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    token_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    subscription_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    support_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    security_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    announcement_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    minimum_priority: Mapped[str] = mapped_column(
        String(30),
        default="low",
        nullable=False,
        index=True,
    )

    email_minimum_priority: Mapped[str] = mapped_column(
        String(30),
        default="normal",
        nullable=False,
    )

    web_push_minimum_priority: Mapped[str] = mapped_column(
        String(30),
        default="normal",
        nullable=False,
    )

    quiet_hours_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    quiet_hours_start: Mapped[time | None] = mapped_column(
        Time,
        nullable=True,
    )

    quiet_hours_end: Mapped[time | None] = mapped_column(
        Time,
        nullable=True,
    )

    timezone: Mapped[str] = mapped_column(
        String(100),
        default="America/Mexico_City",
        nullable=False,
    )

    allow_urgent_during_quiet_hours: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    disabled_event_types_json: Mapped[str | None] = mapped_column(
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
            name="uq_user_notification_preferences_user",
        ),
        Index(
            "ix_user_notification_preferences_channels",
            "in_app_enabled",
            "email_enabled",
            "web_push_enabled",
        ),
    )