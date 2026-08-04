from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.time import utc_now
from app.db.database import Base


class ProviderGpuPrice(Base):
    __tablename__ = "provider_gpu_prices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    gpu_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    cost_usd_per_second: Mapped[Decimal] = mapped_column(Numeric(18, 9), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    __table_args__ = (
        Index("uq_provider_gpu_prices_provider_gpu", "provider", "gpu_key", unique=True),
    )
