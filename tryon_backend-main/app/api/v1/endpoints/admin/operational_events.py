from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
)
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import (
    admin_guard,
)
from app.models.user import User
from app.schemas.operational_event import (
    OperationalEventListResponse,
    OperationalEventResolveRequest,
    OperationalEventResponse,
    OperationalEventSummaryResponse,
)
from app.services.audit_service import (
    audit_service,
)
from app.services.operational_event_service import (
    operational_event_service,
)


router = APIRouter()


@router.get(
    "/operational-events",
    response_model=OperationalEventListResponse,
)
def list_operational_events(
    source: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    is_resolved: bool | None = Query(
        default=None
    ),
    correlation_id: str | None = Query(
        default=None
    ),
    user_id: int | None = Query(default=None),
    background_job_id: int | None = Query(
        default=None
    ),
    tryon_job_id: int | None = Query(
        default=None
    ),
    search: str | None = Query(default=None),
    created_from: datetime | None = Query(
        default=None
    ),
    created_to: datetime | None = Query(
        default=None
    ),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    return operational_event_service.list_events(
        db,
        source=source,
        severity=severity,
        event_type=event_type,
        is_resolved=is_resolved,
        correlation_id=correlation_id,
        user_id=user_id,
        background_job_id=background_job_id,
        tryon_job_id=tryon_job_id,
        search=search,
        created_from=created_from,
        created_to=created_to,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/operational-events/summary",
    response_model=(
        OperationalEventSummaryResponse
    ),
)
def get_operational_event_summary(
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    return operational_event_service.summary(
        db
    )


@router.get(
    "/operational-events/{event_id}",
    response_model=OperationalEventResponse,
)
def get_operational_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    event = operational_event_service.get(
        db,
        event_id=event_id,
    )

    return (
        operational_event_service
        ._response(event)
    )


@router.post(
    "/operational-events/{event_id}/resolve",
    response_model=OperationalEventResponse,
)
def resolve_operational_event(
    event_id: int,
    data: OperationalEventResolveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    result = operational_event_service.resolve(
        db,
        event_id=event_id,
        resolved_by_user_id=(
            current_admin.id
        ),
        resolution_note=(
            data.resolution_note
        ),
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action=(
            "admin_operational_event_resolved"
        ),
        entity_type="operational_event",
        entity_id=str(event_id),
        description=(
            f"Resolved operational event "
            f"{event_id}."
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