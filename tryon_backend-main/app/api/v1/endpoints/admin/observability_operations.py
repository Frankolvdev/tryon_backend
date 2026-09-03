from fastapi import (
    APIRouter,
    Depends,
    Request,
)
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import (
    admin_guard,
)
from app.models.user import User
from app.schemas.observability_maintenance import (
    ObservabilitySelfTestResponse,
    OperationalEventRetentionRequest,
    OperationalEventRetentionResponse,
)
from app.services.audit_service import (
    audit_service,
)
from app.services.observability_self_test_service import (
    observability_self_test_service,
)
from app.services.operational_event_retention_service import (
    operational_event_retention_service,
)


router = APIRouter()


@router.post(
    "/observability/retention",
    response_model=(
        OperationalEventRetentionResponse
    ),
)
def run_operational_event_retention(
    data: OperationalEventRetentionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    result = (
        operational_event_retention_service
        .run(
            db,
            data=data,
        )
    )

    audit_service.create_log(
        db,
        actor_user_id=(
            current_admin.id
        ),
        action=(
            "admin_observability_retention"
        ),
        entity_type="operational_event",
        entity_id=None,
        description=(
            "Executed operational-event "
            f"retention. Deleted "
            f"{result.total_deleted} records."
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


@router.post(
    "/observability/self-test",
    response_model=(
        ObservabilitySelfTestResponse
    ),
)
def run_observability_self_test(
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    result = (
        observability_self_test_service
        .run(db)
    )

    audit_service.create_log(
        db,
        actor_user_id=(
            current_admin.id
        ),
        action=(
            "admin_observability_self_test"
        ),
        entity_type="observability",
        entity_id=None,
        description=(
            "Executed observability self-test. "
            f"Success: {result.success}."
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