from datetime import datetime

from sqlalchemy import (
    Boolean,
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


class UserAccountSecurity(Base):
    __tablename__ = "user_account_security"

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

    account_status: Mapped[str] = mapped_column(
        String(40),
        default="pending_verification",
        nullable=False,
        index=True,
    )

    email_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )

    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    verification_required: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    failed_login_attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )

    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    last_login_ip: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    terms_accepted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    terms_version: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    terms_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    age_confirmed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    age_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
        index=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            name="uq_user_account_security_user",
        ),
        Index(
            "ix_user_account_security_status",
            "account_status",
            "email_verified",
            "locked_until",
        ),
    )