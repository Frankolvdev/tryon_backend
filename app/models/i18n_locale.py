from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.time import utc_now
from app.db.database import Base


class I18nLocale(Base):
    __tablename__ = "i18n_locales"

    code: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    native_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    fallback_locale_code: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        index=True,
    )

    currency_code: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="USD",
    )

    timezone: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="UTC",
    )

    date_format: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="YYYY-MM-DD",
    )

    time_format: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="HH:mm",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    __table_args__ = (
        Index(
            "ix_i18n_locales_active_default",
            "is_active",
            "is_default",
        ),
    )