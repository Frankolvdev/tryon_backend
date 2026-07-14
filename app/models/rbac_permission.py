from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import RbacAction, RbacModule
from app.common.time import utc_now
from app.db.database import Base


class RbacPermission(Base):
    __tablename__ = "rbac_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    key: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)

    module: Mapped[str] = mapped_column(
        String(100),
        default=RbacModule.ADMIN.value,
        nullable=False,
        index=True,
    )

    action: Mapped[str] = mapped_column(
        String(100),
        default=RbacAction.READ.value,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_system: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )