from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.support import SupportTicketAdminUpdate, SupportTicketResponse
from app.services.audit_service import audit_service
from app.services.support_service import support_service

router = APIRouter()


@router.get("/support-tickets", response_model=list[SupportTicketResponse])
def list_support_tickets(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
):
    return support_service.admin_list_tickets(
        db=db,
        skip=skip,
        limit=limit,
    )


@router.get("/support-tickets/{ticket_id}", response_model=SupportTicketResponse)
def get_support_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return support_service.admin_get_ticket(
        db=db,
        ticket_id=ticket_id,
    )


@router.patch("/support-tickets/{ticket_id}", response_model=SupportTicketResponse)
def update_support_ticket(
    ticket_id: int,
    data: SupportTicketAdminUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    ticket = support_service.admin_update_ticket(
        db=db,
        ticket_id=ticket_id,
        data=data,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_support_ticket_updated",
        entity_type="support_ticket",
        entity_id=str(ticket.id),
        description="Admin updated support ticket.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return ticket