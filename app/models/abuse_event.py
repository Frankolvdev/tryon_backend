from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.rate_limit_enums import (
    AbuseEventStatus,
    AbuseEventType,
    AbuseSeverity,
)
from app.common.time import utc_now
from app.db.database import Base


class AbuseEvent(Base):
    __tablename__ = "abuse_events"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    event_type: Mapped[str] = mapped_column(
        String(100),
        default=AbuseEventType.SUSPICIOUS_REQUEST.value,
        nullable=False,
        index=True,
    )

    severity: Mapped[str] = mapped_column(
        String(30),
        default=AbuseSeverity.LOW.value,
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default=AbuseEventStatus.OPEN.value,
        nullable=False,
        index=True,
    )

    rate_limit_policy_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "rate_limit_policies.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    api_key_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "api_keys.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    ip_address: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    user_agent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    route: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        index=True,
    )

    http_method: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    identifier: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        index=True,
    )

    request_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    request_limit: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    window_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    blocked_until: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )

    details_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    resolution_notes: Mapped[str | None] = mapped_column(
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