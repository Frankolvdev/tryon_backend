from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import StorageProvider
from app.common.time import utc_now
from app.db.database import Base


class StorageFile(Base):
    __tablename__ = "storage_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    provider: Mapped[str] = mapped_column(
        String(50),
        default=StorageProvider.LOCAL.value,
        nullable=False,
        index=True,
    )

    bucket: Mapped[str | None] = mapped_column(String(255), nullable=True)
    object_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    public_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )