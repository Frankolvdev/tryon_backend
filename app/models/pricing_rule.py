from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import PricingOperationType, QualityMode, TryOnItemType
from app.common.time import utc_now
from app.db.database import Base


class PricingRule(Base):
    __tablename__ = "pricing_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    operation_type: Mapped[str] = mapped_column(
        String(50),
        default=PricingOperationType.TRYON.value,
        nullable=False,
        index=True,
    )

    item_type: Mapped[str] = mapped_column(
        String(50),
        default=TryOnItemType.CLOTHING.value,
        nullable=False,
        index=True,
    )

    quality_mode: Mapped[str] = mapped_column(
        String(50),
        default=QualityMode.STANDARD.value,
        nullable=False,
        index=True,
    )

    tokens_cost: Mapped[int] = mapped_column(Integer, nullable=False)

    estimated_gpu_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    estimated_gpu_cost_cents: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    margin_percent: Mapped[int] = mapped_column(Integer, default=70, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )