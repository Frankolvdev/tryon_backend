from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.auth_guard import auth_guard
from app.models.user import User
from app.schemas.subscription import (
    SubscriptionActionResponse,
    SubscriptionCancelRequest,
    SubscriptionChangePlanRequest,
    SubscriptionCheckoutRequest,
    SubscriptionCheckoutResponse,
    SubscriptionPortalRequest,
    SubscriptionPortalResponse,
    SubscriptionReactivateRequest,
    SubscriptionSyncResponse,
    UserSubscriptionResponse,
)
from app.schemas.token_purchase import (
    TokenPurchaseCheckoutRequest,
    TokenPurchaseCheckoutResponse,
    TokenPurchaseDetailResponse,
    TokenPurchaseListResponse,
)
from app.services.billing_service import billing_service
from app.services.subscription_service import subscription_service
from app.services.token_purchase_service import (
    token_purchase_service,
)

router = APIRouter()


@router.post(
    "/checkout/tokens",
    response_model=TokenPurchaseCheckoutResponse,
)
def create_token_checkout(
    data: TokenPurchaseCheckoutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return billing_service.create_token_checkout(
        db=db,
        user=current_user,
        data=data,
    )


@router.get(
    "/token-purchases",
    response_model=TokenPurchaseListResponse,
)
def list_my_token_purchases(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return token_purchase_service.list_user_purchases(
        db,
        user_id=current_user.id,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/token-purchases/{purchase_id}",
    response_model=TokenPurchaseDetailResponse,
)
def get_my_token_purchase(
    purchase_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return token_purchase_service.get_detail(
        db,
        purchase_id=purchase_id,
        user_id=current_user.id,
    )


@router.post(
    "/subscriptions/checkout",
    response_model=SubscriptionCheckoutResponse,
)
def create_subscription_checkout(
    data: SubscriptionCheckoutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return subscription_service.create_checkout(
        db,
        user=current_user,
        data=data,
    )


@router.get(
    "/subscriptions/current",
    response_model=UserSubscriptionResponse,
)
def get_current_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return subscription_service.get_current_response(
        db,
        user_id=current_user.id,
    )


@router.post(
    "/subscriptions/cancel",
    response_model=SubscriptionActionResponse,
)
def cancel_subscription(
    data: SubscriptionCancelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    if data.cancel_immediately:
        return subscription_service.cancel_immediately(
            db,
            user_id=current_user.id,
        )

    return subscription_service.cancel_at_period_end(
        db,
        user_id=current_user.id,
    )


@router.post(
    "/subscriptions/reactivate",
    response_model=SubscriptionActionResponse,
)
def reactivate_subscription(
    data: SubscriptionReactivateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    if not data.confirm:
        from app.common.exceptions import ConflictException

        raise ConflictException(
            "Subscription reactivation was not confirmed."
        )

    return subscription_service.reactivate(
        db,
        user_id=current_user.id,
    )


@router.post(
    "/subscriptions/change-plan",
    response_model=SubscriptionActionResponse,
)
def change_subscription_plan(
    data: SubscriptionChangePlanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return subscription_service.change_plan(
        db,
        user_id=current_user.id,
        data=data,
    )


@router.post(
    "/subscriptions/sync",
    response_model=SubscriptionSyncResponse,
)
def synchronize_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return subscription_service.synchronize_subscription(
        db,
        user_id=current_user.id,
    )


@router.post(
    "/customer-portal",
    response_model=SubscriptionPortalResponse,
)
def create_customer_portal(
    data: SubscriptionPortalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return subscription_service.create_portal(
        db,
        user=current_user,
        return_url=str(data.return_url),
    )