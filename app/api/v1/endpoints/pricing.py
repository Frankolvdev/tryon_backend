from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.common.enums import QualityMode, TryOnItemType
from app.schemas.pricing import PricingEstimateResponse
from app.services.pricing_service import pricing_service

router = APIRouter()


@router.get("/tryon-estimate", response_model=PricingEstimateResponse)
def get_tryon_price_estimate(
    item_type: TryOnItemType = Query(...),
    quality_mode: QualityMode = Query(default=QualityMode.STANDARD),
    db: Session = Depends(get_db),
):
    rule = pricing_service.get_tryon_price(
        db, item_type=item_type, quality_mode=quality_mode
    )
    return PricingEstimateResponse(
        operation_type=rule.operation_type,
        item_type=rule.item_type,
        quality_mode=rule.quality_mode,
        tokens_cost=rule.required_tokens,
        final_price_usd=rule.final_price_usd,
        currency=rule.currency,
    )
