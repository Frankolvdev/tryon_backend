from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.time import utc_now
from app.db.database import Base


class AdminMfaCredential(Base):
    __tablename__ = "admin_mfa_credentials"

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

    method: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="totp",
    )

    secret_encrypted: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    recovery_codes_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )

    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    last_used_at: Mapped[datetime | None] = mapped_column(
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