from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.job_enums import JobDependencyType
from app.common.time import utc_now
from app.db.database import Base


class BackgroundJobDependency(Base):
    __tablename__ = "background_job_dependencies"

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

    depends_on_job_id: Mapped[int] = mapped_column(
        ForeignKey(
            "background_jobs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    dependency_type: Mapped[str] = mapped_column(
        String(50),
        default=JobDependencyType.SUCCESS.value,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )

    __table_args__ = (
        Index(
            "ix_background_job_dependency_unique",
            "background_job_id",
            "depends_on_job_id",
            unique=True,
        ),
    )