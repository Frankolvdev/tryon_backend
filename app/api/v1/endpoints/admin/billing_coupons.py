from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.billing_coupon import (
    BillingCouponCreate,
    BillingCouponListResponse,
    BillingCouponResponse,
    BillingCouponSyncResponse,
    BillingCouponUpdate,
)
from app.services.audit_service import audit_service
from app.services.billing_coupon_service import (
    billing_coupon_service,
)

router = APIRouter()


@router.get(
    "/billing-coupons",
    response_model=BillingCouponListResponse,
)
def list_billing_coupons(
    search: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return billing_coupon_service.list_coupons(
        db,
        search=search,
        is_active=is_active,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/billing-coupons",
    response_model=BillingCouponResponse,
    status_code=201,
)
def create_billing_coupon(
    data: BillingCouponCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = billing_coupon_service.create_coupon(
        db,
        data=data,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_billing_coupon_created",
        entity_type="billing_coupon",
        entity_id=str(result.id),
        description=f"Created billing coupon {result.code}.",
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get("user-agent"),
    )

    return result


@router.patch(
    "/billing-coupons/{coupon_id}",
    response_model=BillingCouponResponse,
)
def update_billing_coupon(
    coupon_id: int,
    data: BillingCouponUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = billing_coupon_service.update_coupon(
        db,
        coupon_id=coupon_id,
        data=data,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_billing_coupon_updated",
        entity_type="billing_coupon",
        entity_id=str(result.id),
        description=f"Updated billing coupon {result.code}.",
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get("user-agent"),
    )

    return result


@router.post(
    "/billing-coupons/{coupon_id}/sync-stripe",
    response_model=BillingCouponSyncResponse,
)
def sync_billing_coupon(
    coupon_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = billing_coupon_service.sync_with_stripe(
        db,
        coupon_id=coupon_id,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_billing_coupon_synced",
        entity_type="billing_coupon",
        entity_id=str(coupon_id),
        description="Synchronized billing coupon with Stripe.",
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get("user-agent"),
    )

    return result


@router.post(
    "/billing-coupons/{coupon_id}/activate",
    response_model=BillingCouponResponse,
)
def activate_billing_coupon(
    coupon_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return billing_coupon_service.set_active(
        db,
        coupon_id=coupon_id,
        active=True,
    )


@router.post(
    "/billing-coupons/{coupon_id}/deactivate",
    response_model=BillingCouponResponse,
)
def deactivate_billing_coupon(
    coupon_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return billing_coupon_service.set_active(
        db,
        coupon_id=coupon_id,
        active=False,
    )