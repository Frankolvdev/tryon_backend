from datetime import datetime

from sqlalchemy import (
    JSON,
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


class AuditEntry(Base):
    __tablename__ = "audit_entries"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    actor_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    actor_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="system",
        index=True,
    )

    action: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        index=True,
    )

    entity_type: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        index=True,
    )

    entity_id: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        index=True,
    )

    success: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )

    before_data: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    after_data: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    diff_data: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    metadata_json: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    ip_address: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    user_agent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    correlation_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    request_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    error_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    is_restorable: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )

    restored_from_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "audit_entries.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index(
            "ix_audit_entries_actor_date",
            "actor_user_id",
            "created_at",
        ),
        Index(
            "ix_audit_entries_entity",
            "entity_type",
            "entity_id",
        ),
        Index(
            "ix_audit_entries_action_date",
            "action",
            "created_at",
        ),
        Index(
            "ix_audit_entries_entity_date",
            "entity_type",
            "entity_id",
            "created_at",
        ),
        Index(
            "ix_audit_entries_result_date",
            "success",
            "created_at",
        ),
    )