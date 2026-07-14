from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.time import utc_now
from app.db.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    actor_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    action: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    ip_address: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
        index=True,
    )