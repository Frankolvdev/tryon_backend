from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.time import utc_now
from app.db.database import Base


class AccountSecuritySetting(Base):
    __tablename__ = "account_security_settings"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        default=1,
    )

    registration_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    verification_required: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    verification_method: Mapped[str] = mapped_column(
        String(40),
        default="otp_and_email_link",
        nullable=False,
    )
    allow_login_before_verification: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    otp_length: Mapped[int] = mapped_column(
        Integer,
        default=6,
        nullable=False,
    )
    otp_expiration_minutes: Mapped[int] = mapped_column(
        Integer,
        default=15,
        nullable=False,
    )
    otp_max_attempts: Mapped[int] = mapped_column(
        Integer,
        default=5,
        nullable=False,
    )
    otp_resend_cooldown_seconds: Mapped[int] = mapped_column(
        Integer,
        default=60,
        nullable=False,
    )
    otp_max_resends_per_hour: Mapped[int] = mapped_column(
        Integer,
        default=5,
        nullable=False,
    )
    email_link_expiration_minutes: Mapped[int] = mapped_column(
        Integer,
        default=60,
        nullable=False,
    )

    delete_unverified_accounts_after_days: Mapped[int] = mapped_column(
        Integer,
        default=7,
        nullable=False,
    )
    turnstile_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    block_disposable_email: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    require_terms_acceptance: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    require_age_confirmation: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    minimum_age: Mapped[int] = mapped_column(
        Integer,
        default=18,
        nullable=False,
    )
    max_accounts_per_ip_per_day: Mapped[int] = mapped_column(
        Integer,
        default=3,
        nullable=False,
    )
    max_registrations_per_device_per_day: Mapped[int] = mapped_column(
        Integer,
        default=2,
        nullable=False,
    )

    # BackOffice / administrative accounts.
    admin_mfa_required: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    admin_mfa_totp_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    admin_mfa_recovery_codes_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # End-user frontend accounts.
    user_mfa_available: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    user_mfa_required: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    user_mfa_totp_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    user_mfa_recovery_codes_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
