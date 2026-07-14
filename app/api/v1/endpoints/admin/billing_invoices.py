from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.common.billing_enums import BillingInvoiceStatus
from app.models.user import User
from app.schemas.billing_history import (
    BillingInvoiceDocumentResponse,
    BillingInvoiceHistoryListResponse,
    BillingInvoiceHistoryResponse,
)
from app.services.billing_history_service import (
    billing_history_service,
)

router = APIRouter()


@router.get(
    "/billing-invoices",
    response_model=BillingInvoiceHistoryListResponse,
)
def list_billing_invoices(
    user_id: int | None = Query(default=None),
    status: BillingInvoiceStatus | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return billing_history_service.list_invoices(
        db,
        user_id=user_id,
        status=status,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/billing-invoices/{invoice_id}",
    response_model=BillingInvoiceHistoryResponse,
)
def get_billing_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return billing_history_service.get_invoice_response(
        db,
        invoice_id=invoice_id,
    )


@router.get(
    "/billing-invoices/{invoice_id}/documents",
    response_model=BillingInvoiceDocumentResponse,
)
def get_billing_invoice_documents(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return billing_history_service.get_invoice_documents(
        db,
        invoice_id=invoice_id,
    )