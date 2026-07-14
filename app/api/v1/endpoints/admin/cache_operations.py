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
from app.schemas.cache_health import (
    CacheHealthCheckResponse,
    CacheMaintenanceRequest,
    CacheMaintenanceResponse,
    CacheServerMetrics,
    CacheTtlPolicyResponse,
)
from app.services.audit_service import (
    audit_service,
)
from app.services.cache_health_service import (
    cache_health_service,
)
from app.services.cache_maintenance_service import (
    cache_maintenance_service,
)
from app.services.cache_server_metrics_service import (
    cache_server_metrics_service,
)


router = APIRouter()


@router.get(
    "/cache-operations/health",
    response_model=(
        CacheHealthCheckResponse
    ),
)
def get_cache_health(
    current_admin: User = Depends(
        admin_guard
    ),
):
    return (
        cache_health_service
        .run_health_check()
    )


@router.get(
    "/cache-operations/server-metrics",
    response_model=CacheServerMetrics,
)
def get_cache_server_metrics(
    current_admin: User = Depends(
        admin_guard
    ),
):
    return (
        cache_server_metrics_service
        .get_metrics()
    )


@router.get(
    "/cache-operations/ttl-policies",
    response_model=CacheTtlPolicyResponse,
)
def get_cache_ttl_policies(
    current_admin: User = Depends(
        admin_guard
    ),
):
    return (
        cache_health_service
        .ttl_policies()
    )


@router.post(
    "/cache-operations/maintenance",
    response_model=(
        CacheMaintenanceResponse
    ),
)
def run_cache_maintenance(
    data: CacheMaintenanceRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    result = (
        cache_maintenance_service
        .run(
            data=data
        )
    )

    audit_service.create_log(
        db,
        actor_user_id=(
            current_admin.id
        ),
        action=(
            "admin_cache_maintenance"
        ),
        entity_type="cache",
        entity_id=None,
        description=(
            "Executed cache maintenance. "
            f"Orphan members removed: "
            f"{result.orphan_members_removed}; "
            f"empty tag sets deleted: "
            f"{result.empty_tag_sets_deleted}; "
            f"namespace keys deleted: "
            f"{result.namespace_deleted_keys}."
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