from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import SettingCategory, SettingValueType
from app.common.time import utc_now
from app.db.database import Base


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    category: Mapped[str] = mapped_column(
        String(100),
        default=SettingCategory.SYSTEM.value,
        nullable=False,
        index=True,
    )

    key: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    value_type: Mapped[str] = mapped_column(
        String(50),
        default=SettingValueType.STRING.value,
        nullable=False,
        index=True,
    )

    value_string: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_integer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    value_float: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_boolean: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    value_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    default_value_string: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_value_integer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    default_value_float: Mapped[float | None] = mapped_column(Float, nullable=True)
    default_value_boolean: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    default_value_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_editable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requires_restart: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

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