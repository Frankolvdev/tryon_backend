from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import WebhookDeliveryStatus
from app.common.time import utc_now
from app.db.database import Base


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    webhook_event_id: Mapped[int] = mapped_column(
        ForeignKey("webhook_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    webhook_endpoint_id: Mapped[int] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default=WebhookDeliveryStatus.PENDING.value,
        nullable=False,
        index=True,
    )

    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    request_headers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_body_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
        index=True,
    )