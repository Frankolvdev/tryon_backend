from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.time import utc_now
from app.db.database import Base


class RuntimeBuilderConfig(Base):
    __tablename__ = "runtime_builder_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), default="Runtime principal", nullable=False)
    runtime_version: Mapped[str] = mapped_column(String(64), default="1.0.0", nullable=False)
    python_version: Mapped[str] = mapped_column(String(32), default="3.11", nullable=False)
    cuda_version: Mapped[str] = mapped_column(String(32), default="12.4.1", nullable=False)
    pytorch_index_url: Mapped[str] = mapped_column(
        String(1000), default="https://download.pytorch.org/whl/cu124", nullable=False
    )
    comfyui_repository: Mapped[str] = mapped_column(
        String(1000), default="https://github.com/comfyanonymous/ComfyUI.git", nullable=False
    )
    comfyui_commit: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_platform: Mapped[str] = mapped_column(String(64), default="linux/amd64", nullable=False)
    registry_image: Mapped[str] = mapped_column(
        String(500), default="ghcr.io/your-org/tryon-generation-runtime", nullable=False
    )
    include_comfyui_manager: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    custom_nodes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    python_dependencies: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    models: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    environment_variables: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    volumes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
