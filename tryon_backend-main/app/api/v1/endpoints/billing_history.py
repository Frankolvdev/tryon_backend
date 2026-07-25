from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.auth_guard import auth_guard
from app.common.billing_enums import (
    BillingInvoiceStatus,
    BillingPaymentStatus,
)
from app.models.user import User
from app.schemas.billing_history import (
    BillingInvoiceDocumentResponse,
    BillingInvoiceHistoryListResponse,
    BillingInvoiceHistoryResponse,
    BillingPaymentHistoryListResponse,
    BillingPaymentHistoryResponse,
)
from app.services.billing_history_service import (
    billing_history_service,
)

router = APIRouter()


@router.get(
    "/payments",
    response_model=BillingPaymentHistoryListResponse,
)
def list_my_billing_payments(
    status: BillingPaymentStatus | None = Query(default=None),
    payment_type: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return billing_history_service.list_payments(
        db,
        user_id=current_user.id,
        status=status,
        payment_type=payment_type,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/payments/{payment_id}",
    response_model=BillingPaymentHistoryResponse,
)
def get_my_billing_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return billing_history_service.get_payment_response(
        db,
        payment_id=payment_id,
        user_id=current_user.id,
    )


@router.get(
    "/invoices",
    response_model=BillingInvoiceHistoryListResponse,
)
def list_my_billing_invoices(
    status: BillingInvoiceStatus | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return billing_history_service.list_invoices(
        db,
        user_id=current_user.id,
        status=status,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/invoices/{invoice_id}",
    response_model=BillingInvoiceHistoryResponse,
)
def get_my_billing_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return billing_history_service.get_invoice_response(
        db,
        invoice_id=invoice_id,
        user_id=current_user.id,
    )


@router.get(
    "/invoices/{invoice_id}/documents",
    response_model=BillingInvoiceDocumentResponse,
)
def get_my_invoice_documents(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return billing_history_service.get_invoice_documents(
        db,
        invoice_id=invoice_id,
        user_id=current_user.id,
    )