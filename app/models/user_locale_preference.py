from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.time import utc_now
from app.db.database import Base


class UserLocalePreference(Base):
    __tablename__ = "user_locale_preferences"

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
        unique=True,
        index=True,
    )

    locale_code: Mapped[str] = mapped_column(
        ForeignKey(
            "i18n_locales.code",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    timezone: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    currency_code: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )

    date_format: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    time_format: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
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
        UniqueConstraint(
            "user_id",
            name="uq_user_locale_preferences_user",
        ),
        Index(
            "ix_user_locale_preferences_locale_user",
            "locale_code",
            "user_id",
        ),
    )