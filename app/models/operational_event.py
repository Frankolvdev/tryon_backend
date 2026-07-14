from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.time import utc_now
from app.db.database import Base


class OperationalEvent(Base):
    __tablename__ = "operational_events"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    event_type: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
    )

    source: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    severity: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    correlation_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    user_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )

    background_job_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )

    tryon_job_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )

    provider_job_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    exception_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    exception_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    details_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    is_resolved: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )

    resolved_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    resolution_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index(
            "ix_operational_events_source_severity_created",
            "source",
            "severity",
            "created_at",
        ),
        Index(
            "ix_operational_events_unresolved",
            "is_resolved",
            "severity",
            "created_at",
        ),
    )