from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import ScheduledJobRunStatus
from app.common.time import utc_now
from app.db.database import Base


class ScheduledJobRun(Base):
    __tablename__ = "scheduled_job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    scheduled_job_id: Mapped[int] = mapped_column(
        ForeignKey("scheduled_jobs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default=ScheduledJobRunStatus.PENDING.value,
        nullable=False,
        index=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)