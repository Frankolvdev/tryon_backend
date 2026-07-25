from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import RunPodMode
from app.common.time import utc_now
from app.db.database import Base


class RunPodConfig(Base):
    __tablename__ = "runpod_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    mode: Mapped[str] = mapped_column(
        String(50),
        default=RunPodMode.SERVERLESS.value,
        nullable=False,
    )

    endpoint_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    endpoint_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    gpu_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    docker_image: Mapped[str | None] = mapped_column(String(500), nullable=True)
    comfy_workflow_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    min_workers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_workers: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    estimated_cost_per_second_cents: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )