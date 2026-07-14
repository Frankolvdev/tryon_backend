from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import ApiKeyStatus, ApiKeyType
from app.common.time import utc_now
from app.db.database import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    key_prefix: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
    )

    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    api_key_type: Mapped[str] = mapped_column(
        String(50),
        default=ApiKeyType.INTEGRATION.value,
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default=ApiKeyStatus.ACTIVE.value,
        nullable=False,
        index=True,
    )

    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    scopes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    allowed_ips_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )