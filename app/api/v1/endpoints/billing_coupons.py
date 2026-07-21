from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.schemas.billing_coupon import (
    BillingCouponValidationRequest,
    BillingCouponValidationResponse,
)
from app.services.billing_coupon_service import (
    billing_coupon_service,
)

router = APIRouter()


@router.post(
    "/validate",
    response_model=BillingCouponValidationResponse,
)
def validate_billing_coupon(
    data: BillingCouponValidationRequest,
    db: Session = Depends(get_db),
):
    return billing_coupon_service.validate_code(
        db,
        code=data.code,
        purchase_amount=data.purchase_amount,
        purchase_type=data.purchase_type,
        item_id=data.item_id,
    )