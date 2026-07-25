from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.generation_module_enums import GenerationExecutionEngine
from app.common.time import utc_now
from app.db.database import Base


class GenerationModule(Base):
    __tablename__ = "generation_modules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    category: Mapped[str] = mapped_column(
        String(100), default="tryon", nullable=False, index=True
    )
    default_execution_engine: Mapped[str] = mapped_column(
        String(50),
        default=GenerationExecutionEngine.SIMULATED.value,
        nullable=False,
        index=True,
    )
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    inputs: Mapped[list["GenerationModuleInput"]] = relationship(
        back_populates="module",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="GenerationModuleInput.position",
    )
    outputs: Mapped[list["GenerationModuleOutput"]] = relationship(
        back_populates="module",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="GenerationModuleOutput.position",
    )
    steps: Mapped[list["GenerationModuleStep"]] = relationship(
        back_populates="module",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="GenerationModuleStep.position",
    )

    __table_args__ = (
        Index("ix_generation_modules_key_version", "key", "version", unique=True),
        Index("ix_generation_modules_category_active", "category", "is_active"),
    )


class GenerationModuleInput(Base):
    __tablename__ = "generation_module_inputs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    generation_module_id: Mapped[int] = mapped_column(
        ForeignKey("generation_modules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(150), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_type: Mapped[str] = mapped_column(String(50), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    default_value_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    module: Mapped[GenerationModule] = relationship(back_populates="inputs")

    __table_args__ = (
        Index("ix_generation_module_inputs_module_key", "generation_module_id", "key", unique=True),
        Index("ix_generation_module_inputs_module_position", "generation_module_id", "position"),
    )


class GenerationModuleOutput(Base):
    __tablename__ = "generation_module_outputs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    generation_module_id: Mapped[int] = mapped_column(
        ForeignKey("generation_modules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(150), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_type: Mapped[str] = mapped_column(String(50), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source_step_key: Mapped[str | None] = mapped_column(String(150), nullable=True)
    source_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    module: Mapped[GenerationModule] = relationship(back_populates="outputs")

    __table_args__ = (
        Index("ix_generation_module_outputs_module_key", "generation_module_id", "key", unique=True),
        Index("ix_generation_module_outputs_module_position", "generation_module_id", "position"),
    )


class GenerationModuleStep(Base):
    __tablename__ = "generation_module_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    generation_module_id: Mapped[int] = mapped_column(
        ForeignKey("generation_modules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(150), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    step_type: Mapped[str] = mapped_column(String(50), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    configuration_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    input_mapping_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    output_mapping_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    module: Mapped[GenerationModule] = relationship(back_populates="steps")

    __table_args__ = (
        Index("ix_generation_module_steps_module_key", "generation_module_id", "key", unique=True),
        Index("ix_generation_module_steps_module_position", "generation_module_id", "position", unique=True),
    )
