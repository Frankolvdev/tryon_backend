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
from app.schemas.audit_maintenance import (
    AuditAdvancedStatisticsResponse,
    AuditRetentionRequest,
    AuditRetentionResponse,
    AuditSelfTestResponse,
)
from app.services.audit_retention_service import (
    audit_retention_service,
)
from app.services.audit_self_test_service import (
    audit_self_test_service,
)
from app.services.audit_service import (
    audit_service,
)
from app.services.audit_statistics_service import (
    audit_statistics_service,
)


router = APIRouter()


@router.get(
    "/audit-operations/statistics",
    response_model=(
        AuditAdvancedStatisticsResponse
    ),
)
def get_advanced_audit_statistics(
    period_days: int = Query(
        default=30,
        ge=1,
        le=3650,
    ),
    top_limit: int = Query(
        default=10,
        ge=1,
        le=100,
    ),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    return (
        audit_statistics_service
        .advanced_statistics(
            db,
            period_days=period_days,
            top_limit=top_limit,
        )
    )


@router.post(
    "/audit-operations/retention",
    response_model=AuditRetentionResponse,
)
def run_audit_retention(
    data: AuditRetentionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    result = audit_retention_service.run(
        db,
        data=data,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action=(
            "admin_advanced_audit_retention"
        ),
        entity_type="audit_entry",
        entity_id=None,
        description=(
            "Executed advanced audit retention. "
            f"Deleted {result.total_deleted} "
            "entries."
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
    "/audit-operations/self-test",
    response_model=AuditSelfTestResponse,
)
def run_audit_self_test(
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    result = audit_self_test_service.run()

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action=(
            "admin_advanced_audit_self_test"
        ),
        entity_type="audit_entry",
        entity_id=None,
        description=(
            "Executed advanced audit self-test. "
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