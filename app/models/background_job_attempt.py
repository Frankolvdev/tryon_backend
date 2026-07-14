from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.job_enums import JobAttemptStatus
from app.common.time import utc_now
from app.db.database import Base


class BackgroundJobAttempt(Base):
    __tablename__ = "background_job_attempts"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    background_job_id: Mapped[int] = mapped_column(
        ForeignKey(
            "background_jobs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default=JobAttemptStatus.STARTED.value,
        nullable=False,
        index=True,
    )

    worker_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    lease_token: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    provider_job_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    duration_seconds: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    error_code: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    error_details_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    result_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    metrics_json: Mapped[str | None] = mapped_column(
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

    __table_args__ = (
        Index(
            "ix_background_job_attempt_unique",
            "background_job_id",
            "attempt_number",
            unique=True,
        ),
    )