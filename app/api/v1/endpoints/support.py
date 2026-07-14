from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.auth_guard import auth_guard
from app.models.user import User
from app.schemas.support import SupportTicketCreate, SupportTicketResponse
from app.services.support_service import support_service

router = APIRouter()


@router.post("/tickets", response_model=SupportTicketResponse)
def create_support_ticket(
    data: SupportTicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return support_service.create_ticket(
        db=db,
        user=current_user,
        data=data,
    )


@router.get("/tickets", response_model=list[SupportTicketResponse])
def list_my_support_tickets(
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    return support_service.list_my_tickets(
        db=db,
        user=current_user,
        skip=skip,
        limit=limit,
    )


@router.get("/tickets/{ticket_id}", response_model=SupportTicketResponse)
def get_my_support_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return support_service.get_my_ticket(
        db=db,
        user=current_user,
        ticket_id=ticket_id,
    )