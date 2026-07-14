from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import NotificationCategory, NotificationType
from app.common.time import utc_now
from app.db.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    notification_type: Mapped[str] = mapped_column(
        String(50),
        default=NotificationType.INFO.value,
        nullable=False,
        index=True,
    )

    category: Mapped[str] = mapped_column(
        String(50),
        default=NotificationCategory.SYSTEM.value,
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
        index=True,
    )

    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)