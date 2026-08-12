from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.common.time import utc_now
from app.db.database import Base


class BodyProportionWorkflowConfig(Base):
    __tablename__ = "body_proportion_workflow_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sex: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    workflow_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    input_mapping_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    limits_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    formula_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    fixed_values_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    storage_mode: Mapped[str] = mapped_column(String(32), default="auto", nullable=False)
    active_preview_source: Mapped[str] = mapped_column(String(32), default="auto", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class BodyProportionPreset(Base):
    __tablename__ = "body_proportion_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sex: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    sort_order: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    profile_key: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(180), nullable=False)
    category_slug: Mapped[str] = mapped_column(String(180), nullable=False)
    fat_band: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    ass_band: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    breast_band: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    is_base_category: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    base_category_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)

    hips_size: Mapped[float] = mapped_column(Float, nullable=False)
    fat_thin: Mapped[float] = mapped_column(Float, nullable=False)
    breasts_size: Mapped[float] = mapped_column(Float, nullable=False)
    skin_tone: Mapped[float] = mapped_column(Float, nullable=False)
    hair_length: Mapped[float] = mapped_column(Float, nullable=False)

    image_storage_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("storage_files.id", ondelete="SET NULL"), nullable=True, index=True
    )
    preview_storage_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    local_mirror_path: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False, index=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("sex", "profile_key", name="uq_body_proportion_preset_sex_key"),
        UniqueConstraint("sex", "category_slug", name="uq_body_proportion_preset_sex_slug"),
        Index("ix_body_proportion_presets_sex_sort", "sex", "sort_order"),
    )


class BubbleButtWorkflowConfig(Base):
    __tablename__ = "bubble_butt_workflow_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sex: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    workflow_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    input_mapping_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    bubble_values_json: Mapped[list] = mapped_column(JSON, default=lambda: [0.0, 0.4, 0.8, 1.2], nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class BubbleButtPreset(Base):
    __tablename__ = "bubble_butt_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sex: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    sort_order: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    profile_key: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(220), nullable=False)
    category_slug: Mapped[str] = mapped_column(String(220), nullable=False)
    fat_band: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ass_band: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    variant_index: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    hips_size: Mapped[float] = mapped_column(Float, nullable=False)
    fat_thin: Mapped[float] = mapped_column(Float, nullable=False)
    breasts_size: Mapped[float] = mapped_column(Float, nullable=False)
    bubble_butt: Mapped[float] = mapped_column(Float, nullable=False)
    skin_tone: Mapped[float] = mapped_column(Float, nullable=False)
    hair_length: Mapped[float] = mapped_column(Float, nullable=False)

    image_storage_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("storage_files.id", ondelete="SET NULL"), nullable=True, index=True
    )
    preview_storage_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    local_mirror_path: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False, index=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("sex", "profile_key", name="uq_bubble_butt_preset_sex_key"),
        UniqueConstraint("sex", "fat_band", "ass_band", "variant_index", name="uq_bubble_butt_grid"),
        Index("ix_bubble_butt_presets_sex_sort", "sex", "sort_order"),
    )
