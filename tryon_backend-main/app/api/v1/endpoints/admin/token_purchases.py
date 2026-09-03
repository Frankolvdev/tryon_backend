from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.common.billing_enums import TokenPurchaseStatus
from app.models.user import User
from app.schemas.token_purchase import (
    TokenPurchaseDetailResponse,
    TokenPurchaseListResponse,
    TokenPurchaseReconcileRequest,
    TokenPurchaseReconcileResponse,
    TokenPurchaseRefundRequest,
    TokenPurchaseRefundResponse,
)
from app.services.audit_service import audit_service
from app.services.token_purchase_service import (
    token_purchase_service,
)

router = APIRouter()


@router.get(
    "/token-purchases",
    response_model=TokenPurchaseListResponse,
)
def list_token_purchases(
    user_id: int | None = Query(default=None),
    status: TokenPurchaseStatus | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return token_purchase_service.list_admin_purchases(
        db,
        user_id=user_id,
        status=status,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/token-purchases/{purchase_id}",
    response_model=TokenPurchaseDetailResponse,
)
def get_token_purchase(
    purchase_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return token_purchase_service.get_detail(
        db,
        purchase_id=purchase_id,
    )


@router.post(
    "/token-purchases/{purchase_id}/reconcile",
    response_model=TokenPurchaseReconcileResponse,
)
def reconcile_token_purchase(
    purchase_id: int,
    data: TokenPurchaseReconcileRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = token_purchase_service.reconcile(
        db,
        purchase_id=purchase_id,
        force=data.force,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_token_purchase_reconciled",
        entity_type="token_purchase",
        entity_id=str(purchase_id),
        description=(
            f"Admin reconciled token purchase "
            f"{purchase_id} with Stripe."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get("user-agent"),
    )

    return result


@router.post(
    "/token-purchases/{purchase_id}/refund",
    response_model=TokenPurchaseRefundResponse,
)
def refund_token_purchase(
    purchase_id: int,
    data: TokenPurchaseRefundRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = token_purchase_service.refund(
        db,
        purchase_id=purchase_id,
        data=data,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_token_purchase_refunded",
        entity_type="token_purchase",
        entity_id=str(purchase_id),
        description=(
            f"Admin refunded token purchase "
            f"{purchase_id}."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get("user-agent"),
    )

    return result