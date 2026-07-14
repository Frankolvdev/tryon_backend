from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.time import utc_now
from app.db.database import Base


class UserGalleryItem(Base):
    __tablename__ = "user_gallery_items"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    tryon_job_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "tryon_jobs.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    source_file_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "storage_files.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    result_file_id: Mapped[int] = mapped_column(
        ForeignKey(
            "storage_files.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    title: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="tryon",
        index=True,
    )

    visibility: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="private",
        index=True,
    )

    is_favorite: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
        index=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    __table_args__ = (
        Index(
            "ix_user_gallery_owner_state",
            "user_id",
            "is_deleted",
            "is_archived",
        ),
        Index(
            "ix_user_gallery_owner_favorite",
            "user_id",
            "is_favorite",
            "created_at",
        ),
        Index(
            "ix_user_gallery_tryon_owner",
            "tryon_job_id",
            "user_id",
        ),
    )