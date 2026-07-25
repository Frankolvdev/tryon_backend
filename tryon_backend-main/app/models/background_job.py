from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.job_enums import (
    JobExecutionMode,
    JobPriority,
    JobQueueName,
    JobStatus,
)
from app.common.time import utc_now
from app.db.database import Base


class BackgroundJob(Base):
    __tablename__ = "background_jobs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    public_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )

    job_type: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
    )

    queue_name: Mapped[str] = mapped_column(
        String(100),
        default=JobQueueName.DEFAULT.value,
        nullable=False,
        index=True,
    )

    execution_mode: Mapped[str] = mapped_column(
        String(50),
        default=JobExecutionMode.INTERNAL.value,
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default=JobStatus.PENDING.value,
        nullable=False,
        index=True,
    )

    priority: Mapped[int] = mapped_column(
        Integer,
        default=JobPriority.NORMAL.value,
        nullable=False,
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

    tryon_job_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "tryon_jobs.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    external_ai_job_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "external_ai_jobs.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    idempotency_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
        index=True,
    )

    payload_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    result_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    metadata_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    error_code: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        index=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    error_details_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    progress: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )

    progress_message: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    attempt_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    max_attempts: Mapped[int] = mapped_column(
        Integer,
        default=3,
        nullable=False,
    )

    retry_backoff_seconds: Mapped[int] = mapped_column(
        Integer,
        default=30,
        nullable=False,
    )

    retry_backoff_multiplier: Mapped[float] = mapped_column(
        Float,
        default=2.0,
        nullable=False,
    )

    timeout_seconds: Mapped[int] = mapped_column(
        Integer,
        default=900,
        nullable=False,
    )

    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )

    available_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
        index=True,
    )

    queued_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )

    canceled_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )

    lease_owner: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    lease_token: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )

    provider_job_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    provider_endpoint_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    worker_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    worker_version: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    is_cancelable: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    retain_until: Mapped[datetime | None] = mapped_column(
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
            "ix_background_jobs_queue_claim",
            "queue_name",
            "status",
            "available_at",
            "priority",
            "created_at",
        ),
        Index(
            "ix_background_jobs_lease_recovery",
            "status",
            "lease_expires_at",
        ),
        Index(
            "ix_background_jobs_user_created",
            "user_id",
            "created_at",
        ),
    )