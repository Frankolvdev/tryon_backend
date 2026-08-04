from __future__ import annotations

import math
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.exceptions import NotFoundException
from app.models.provider_gpu_price import ProviderGpuPrice
from app.schemas.provider_pricing import ProviderGpuPriceResponse, ProviderGpuPriceUpsert


class ProviderPricingService:
    def list_prices(self, db: Session, *, provider: str | None = None) -> list[ProviderGpuPriceResponse]:
        query = select(ProviderGpuPrice)
        if provider:
            query = query.where(ProviderGpuPrice.provider == provider.strip().lower())
        rows = db.scalars(query.order_by(ProviderGpuPrice.provider, ProviderGpuPrice.gpu_key)).all()
        return [ProviderGpuPriceResponse.model_validate(row) for row in rows]

    def upsert(self, db: Session, data: ProviderGpuPriceUpsert) -> ProviderGpuPriceResponse:
        provider = data.provider.strip().lower()
        gpu_key = data.gpu_key.strip()
        row = db.scalar(
            select(ProviderGpuPrice).where(
                ProviderGpuPrice.provider == provider,
                ProviderGpuPrice.gpu_key == gpu_key,
            )
        )
        payload = data.model_dump()
        payload["provider"] = provider
        payload["gpu_key"] = gpu_key
        payload["cost_usd_per_second"] = Decimal(str(data.cost_usd_per_second))
        if row is None:
            row = ProviderGpuPrice(**payload)
            db.add(row)
        else:
            for key, value in payload.items():
                setattr(row, key, value)
        db.commit()
        db.refresh(row)
        return ProviderGpuPriceResponse.model_validate(row)

    def delete(self, db: Session, price_id: int) -> None:
        row = db.get(ProviderGpuPrice, price_id)
        if row is None:
            raise NotFoundException("Provider GPU price not found.")
        db.delete(row)
        db.commit()

    def get_cost(self, db: Session, *, provider: str, gpu_key: str | None) -> float | None:
        if not gpu_key:
            return None
        row = db.scalar(
            select(ProviderGpuPrice).where(
                ProviderGpuPrice.provider == provider.strip().lower(),
                ProviderGpuPrice.gpu_key == gpu_key.strip(),
                ProviderGpuPrice.is_active.is_(True),
            )
        )
        return float(row.cost_usd_per_second) if row else None


provider_pricing_service = ProviderPricingService()
