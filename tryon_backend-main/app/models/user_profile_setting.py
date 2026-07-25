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


class UserProfileSetting(Base):
    __tablename__ = "user_profile_settings"

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

    username: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        unique=True,
        index=True,
    )

    biography: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    country_code: Mapped[str | None] = mapped_column(
        String(2),
        nullable=True,
        index=True,
    )

    timezone: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="America/Mexico_City",
    )

    locale_code: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="es-MX",
        index=True,
    )

    currency_code: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="MXN",
    )

    profile_visibility: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="private",
        index=True,
    )

    gallery_visibility: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="private",
        index=True,
    )

    show_activity_status: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    allow_marketing_emails: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    allow_product_updates: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    allow_security_emails: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    image_processing_consent: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    image_processing_consent_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    retain_input_images: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    retain_generated_images: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    profile_completed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    onboarding_completed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
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
        Index(
            "ix_user_profile_settings_privacy",
            "profile_visibility",
            "gallery_visibility",
        ),
        Index(
            "ix_user_profile_settings_onboarding",
            "profile_completed",
            "onboarding_completed",
        ),
    )