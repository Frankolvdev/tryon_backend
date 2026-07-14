from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import ScheduledJobStatus
from app.common.time import utc_now
from app.db.database import Base


class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    key: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    cron_expression: Mapped[str] = mapped_column(String(100), nullable=False)

    status: Mapped[str] = mapped_column(
        String(50),
        default=ScheduledJobStatus.ACTIVE.value,
        nullable=False,
        index=True,
    )

    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )