from datetime import datetime
from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.common.time import utc_now
from app.db.database import Base

class RuntimeBuilderBuild(Base):
    __tablename__ = "runtime_builder_builds"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    runtime_config_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    image_tag: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    phase: Mapped[str] = mapped_column(String(64), default="queued", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    logs: Mapped[str] = mapped_column(Text, default="", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    image_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    manifest: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    validation_result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
