from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.time import utc_now
from app.db.database import Base


class WorkflowDefinition(Base):
    __tablename__ = "workflow_definitions"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    key: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )

    category: Mapped[str] = mapped_column(
        String(100),
        default="tryon",
        nullable=False,
        index=True,
    )

    workflow_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    parameter_schema_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    execution_modes_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    metadata_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )

    is_default: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )

    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
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
        Index(
            "ix_workflow_definitions_key_version",
            "key",
            "version",
            unique=True,
        ),
        Index(
            "ix_workflow_definitions_category_default",
            "category",
            "is_default",
            "is_active",
        ),
    )