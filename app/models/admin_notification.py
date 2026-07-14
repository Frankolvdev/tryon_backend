from datetime import datetime

from sqlalchemy import (
    Boolean,
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


class AdminNotification(Base):
    __tablename__ = "admin_notifications"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    recipient_user_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
    )

    notification_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="info",
        index=True,
    )

    priority: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="normal",
        index=True,
    )

    source: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        default="system",
        index=True,
    )

    event_type: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    action_url: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
    )

    action_label: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )

    entity_type: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        index=True,
    )

    entity_id: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
        index=True,
    )

    correlation_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    metadata_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    is_global: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )

    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )

    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )

    requires_action: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )

    read_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    expires_at: Mapped[datetime | None] = mapped_column(
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
            "ix_admin_notifications_recipient_status",
            "recipient_user_id",
            "is_read",
            "is_archived",
            "created_at",
        ),
        Index(
            "ix_admin_notifications_global_status",
            "is_global",
            "is_read",
            "is_archived",
            "created_at",
        ),
        Index(
            "ix_admin_notifications_source_priority",
            "source",
            "priority",
            "created_at",
        ),
        Index(
            "ix_admin_notifications_entity",
            "entity_type",
            "entity_id",
        ),
    )