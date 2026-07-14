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


class AdminNotificationPreference(Base):
    __tablename__ = "admin_notification_preferences"

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

    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )

    minimum_priority: Mapped[str] = mapped_column(
        String(30),
        default="normal",
        nullable=False,
        index=True,
    )

    digest_mode: Mapped[str] = mapped_column(
        String(30),
        default="immediate",
        nullable=False,
        index=True,
    )

    enabled_sources_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    enabled_types_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    quiet_hours_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
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

    allow_critical_during_quiet_hours: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
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
            name=(
                "uq_admin_notification_preferences_user"
            ),
        ),
        Index(
            "ix_admin_notification_preferences_status",
            "is_enabled",
            "minimum_priority",
            "digest_mode",
        ),
    )