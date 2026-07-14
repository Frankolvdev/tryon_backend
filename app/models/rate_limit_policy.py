from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.rate_limit_enums import (
    RateLimitAlgorithm,
    RateLimitScope,
)
from app.common.time import utc_now
from app.db.database import Base


class RateLimitPolicy(Base):
    __tablename__ = "rate_limit_policies"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    key: Mapped[str] = mapped_column(
        String(150),
        unique=True,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    route_pattern: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
    )

    http_method: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        index=True,
    )

    scope: Mapped[str] = mapped_column(
        String(50),
        default=RateLimitScope.IP.value,
        nullable=False,
        index=True,
    )

    algorithm: Mapped[str] = mapped_column(
        String(50),
        default=RateLimitAlgorithm.SLIDING_WINDOW.value,
        nullable=False,
    )

    request_limit: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    window_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    burst_limit: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    block_seconds: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    priority: Mapped[int] = mapped_column(
        Integer,
        default=100,
        nullable=False,
        index=True,
    )

    applies_to_authenticated: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    applies_to_anonymous: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    include_headers: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )

    metadata_json: Mapped[str | None] = mapped_column(
        Text,
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