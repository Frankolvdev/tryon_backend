from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.time import utc_now
from app.db.database import Base


class RuntimeProject(Base):
    __tablename__ = "runtime_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    runtime_config_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    project_key: Mapped[str] = mapped_column(String(120), default="tryon", nullable=False, unique=True, index=True)
    module_type: Mapped[str] = mapped_column(String(120), default="tryon", nullable=False, index=True)
    source_comfyui_path: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    workflow_filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    workflow_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    container_workdir: Mapped[str] = mapped_column(String(1000), default="/app", nullable=False)
    export_root_directory: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    export_directory: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    last_index_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    workspace_status: Mapped[str] = mapped_column(String(64), default="draft", nullable=False)
    last_export_archive: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    last_export_manifest: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_exported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
