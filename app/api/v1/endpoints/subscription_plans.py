from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.common.billing_enums import BillingInterval
from app.schemas.subscription_plan import SubscriptionPlanResponse
from app.services.subscription_plan_service import (
    subscription_plan_service,
)

router = APIRouter()


@router.get(
    "",
    response_model=list[SubscriptionPlanResponse],
)
def list_public_subscription_plans(
    billing_interval: BillingInterval | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return subscription_plan_service.list_public_plans(
        db,
        billing_interval=billing_interval,
    )


@router.get(
    "/{plan_key}",
    response_model=SubscriptionPlanResponse,
)
def get_public_subscription_plan(
    plan_key: str,
    db: Session = Depends(get_db),
):
    plan = subscription_plan_service.get_plan_by_key(
        db,
        plan_key,
        require_active=True,
    )

    if not plan.is_public:
        from app.common.exceptions import NotFoundException

        raise NotFoundException("Subscription plan not found.")

    return subscription_plan_service._to_response(plan)