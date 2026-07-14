from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.common.billing_enums import BillingPaymentStatus
from app.models.user import User
from app.schemas.billing_history import (
    BillingPaymentHistoryListResponse,
    BillingPaymentHistoryResponse,
    BillingPaymentReconcileResponse,
    BillingPaymentRefundRequest,
    BillingPaymentRefundResponse,
)
from app.services.audit_service import audit_service
from app.services.billing_history_service import (
    billing_history_service,
)

router = APIRouter()


@router.get(
    "/billing-payments",
    response_model=BillingPaymentHistoryListResponse,
)
def list_billing_payments(
    user_id: int | None = Query(default=None),
    status: BillingPaymentStatus | None = Query(default=None),
    payment_type: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return billing_history_service.list_payments(
        db,
        user_id=user_id,
        status=status,
        payment_type=payment_type,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/billing-payments/{payment_id}",
    response_model=BillingPaymentHistoryResponse,
)
def get_billing_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return billing_history_service.get_payment_response(
        db,
        payment_id=payment_id,
    )


@router.post(
    "/billing-payments/{payment_id}/reconcile",
    response_model=BillingPaymentReconcileResponse,
)
def reconcile_billing_payment(
    payment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = billing_history_service.reconcile_payment(
        db,
        payment_id=payment_id,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_billing_payment_reconciled",
        entity_type="billing_payment",
        entity_id=str(payment_id),
        description=(
            f"Admin reconciled billing payment {payment_id}."
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
    "/billing-payments/{payment_id}/refund",
    response_model=BillingPaymentRefundResponse,
)
def refund_billing_payment(
    payment_id: int,
    data: BillingPaymentRefundRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = billing_history_service.refund_payment(
        db,
        payment_id=payment_id,
        data=data,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_billing_payment_refunded",
        entity_type="billing_payment",
        entity_id=str(payment_id),
        description=(
            f"Admin refunded billing payment {payment_id}."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get("user-agent"),
    )

    return result