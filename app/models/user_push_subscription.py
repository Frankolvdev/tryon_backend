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


class UserPushSubscription(Base):
    __tablename__ = "user_push_subscriptions"

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

    endpoint: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    endpoint_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )

    p256dh_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    auth_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    user_agent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    device_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )

    failure_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    last_failure_at: Mapped[datetime | None] = mapped_column(
        DateTime,
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
            "endpoint_hash",
            name="uq_user_push_subscriptions_endpoint_hash",
        ),
        Index(
            "ix_user_push_subscriptions_user_active",
            "user_id",
            "is_active",
        ),
    )