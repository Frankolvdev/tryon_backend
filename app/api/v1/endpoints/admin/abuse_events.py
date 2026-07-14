from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import (
    admin_guard,
)
from app.common.rate_limit_enums import (
    AbuseEventStatus,
    AbuseEventType,
    AbuseSeverity,
)
from app.models.user import User
from app.schemas.rate_limit import (
    AbuseEventListResponse,
    AbuseEventResponse,
    AbuseEventReviewRequest,
)
from app.services.abuse_event_service import (
    abuse_event_service,
)
from app.services.audit_service import (
    audit_service,
)

router = APIRouter()


@router.get(
    "/abuse-events",
    response_model=AbuseEventListResponse,
)
def list_abuse_events(
    event_type: AbuseEventType | None = Query(
        default=None
    ),
    severity: AbuseSeverity | None = Query(
        default=None
    ),
    status: AbuseEventStatus | None = Query(
        default=None
    ),
    user_id: int | None = Query(default=None),
    ip_address: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(
        default=100,
        ge=1,
        le=200,
    ),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return abuse_event_service.list_events(
        db,
        event_type=event_type,
        severity=severity,
        status=status,
        user_id=user_id,
        ip_address=ip_address,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/abuse-events/{event_id}",
    response_model=AbuseEventResponse,
)
def get_abuse_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return abuse_event_service.get_response(
        db,
        event_id=event_id,
    )


@router.patch(
    "/abuse-events/{event_id}/review",
    response_model=AbuseEventResponse,
)
def review_abuse_event(
    event_id: int,
    data: AbuseEventReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = abuse_event_service.review_event(
        db,
        event_id=event_id,
        reviewer_user_id=current_admin.id,
        data=data,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_abuse_event_reviewed",
        entity_type="abuse_event",
        entity_id=str(event_id),
        description=(
            f"Reviewed abuse event {event_id} "
            f"with status {data.status.value}."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return result