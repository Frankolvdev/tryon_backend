from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.common.billing_enums import BillingEventStatus
from app.models.user import User
from app.schemas.billing_event import (
    BillingEventListResponse,
    BillingEventRetryResponse,
)
from app.services.audit_service import audit_service
from app.services.billing_event_service import (
    billing_event_service,
)

router = APIRouter()


@router.get(
    "/billing-events",
    response_model=BillingEventListResponse,
)
def list_billing_events(
    event_type: str | None = Query(default=None),
    status: BillingEventStatus | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return billing_event_service.list_events(
        db,
        event_type=event_type,
        status=status,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/billing-events/{event_id}/retry",
    response_model=BillingEventRetryResponse,
)
def retry_billing_event(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = billing_event_service.retry_event(
        db,
        event_id=event_id,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_billing_event_retried",
        entity_type="billing_event",
        entity_id=str(event_id),
        description=f"Retried billing event {event_id}.",
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get("user-agent"),
    )

    return result