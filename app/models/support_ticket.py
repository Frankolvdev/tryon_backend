from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import SupportTicketPriority, SupportTicketStatus
from app.common.time import utc_now
from app.db.database import Base


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(
        String(50),
        default=SupportTicketStatus.OPEN.value,
        nullable=False,
        index=True,
    )

    priority: Mapped[str] = mapped_column(
        String(50),
        default=SupportTicketPriority.MEDIUM.value,
        nullable=False,
        index=True,
    )

    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_admin_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )