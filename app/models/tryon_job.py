from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import QualityMode, TryOnItemType, TryOnJobStatus
from app.common.time import utc_now
from app.db.database import Base


class TryOnJob(Base):
    __tablename__ = "tryon_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    person_image_file_id: Mapped[int] = mapped_column(
        ForeignKey("storage_files.id", ondelete="RESTRICT"),
        nullable=False,
    )

    item_image_file_id: Mapped[int] = mapped_column(
        ForeignKey("storage_files.id", ondelete="RESTRICT"),
        nullable=False,
    )

    result_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("storage_files.id", ondelete="SET NULL"),
        nullable=True,
    )

    pricing_rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("pricing_rules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    runpod_config_id: Mapped[int | None] = mapped_column(
        ForeignKey("runpod_configs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    item_type: Mapped[str] = mapped_column(
        String(50),
        default=TryOnItemType.CLOTHING.value,
        nullable=False,
        index=True,
    )

    quality_mode: Mapped[str] = mapped_column(
        String(50),
        default=QualityMode.STANDARD.value,
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default=TryOnJobStatus.PENDING.value,
        nullable=False,
        index=True,
    )

    tokens_cost: Mapped[int] = mapped_column(Integer, nullable=False, default=10)

    estimated_gpu_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_gpu_cost_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_gpu_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_gpu_cost_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)

    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    runpod_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    comfy_workflow_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)