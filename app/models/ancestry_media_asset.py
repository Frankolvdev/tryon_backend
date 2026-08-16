from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.common.time import utc_now
from app.db.database import Base


class AncestryMediaAsset(Base):
    __tablename__ = "ancestry_media_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ancestry_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(180), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    flag_emoji: Mapped[str | None] = mapped_column(String(16), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    sort_order: Mapped[float] = mapped_column(Float, nullable=False, default=100.0, index=True)
    storage_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="auto")
    poster_storage_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("storage_files.id", ondelete="SET NULL"), nullable=True, index=True
    )
    video_storage_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("storage_files.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint("ancestry_key", name="uq_ancestry_media_assets_key"),
    )
