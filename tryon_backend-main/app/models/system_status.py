from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.time import utc_now
from app.db.database import Base


class SystemStatus(Base):
    __tablename__ = "system_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    registration_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tryon_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    public_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    internal_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    updated_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )