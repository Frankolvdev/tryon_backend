from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.common.rate_limit_enums import RateLimitScope
from app.common.responses import SuccessResponse
from app.models.user import User
from app.schemas.rate_limit import (
    RateLimitPolicyCreate,
    RateLimitPolicyListResponse,
    RateLimitPolicyResponse,
    RateLimitPolicyUpdate,
)
from app.services.audit_service import audit_service
from app.services.default_rate_limit_policies_service import (
    default_rate_limit_policies_service,
)
from app.services.rate_limit_policy_service import (
    rate_limit_policy_service,
)

router = APIRouter()


@router.get(
    "/rate-limits/policies",
    response_model=RateLimitPolicyListResponse,
)
def list_rate_limit_policies(
    search: str | None = Query(default=None),
    is_enabled: bool | None = Query(default=None),
    scope: RateLimitScope | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return rate_limit_policy_service.list_policies(
        db,
        search=search,
        is_enabled=is_enabled,
        scope=scope,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/rate-limits/policies",
    response_model=RateLimitPolicyResponse,
    status_code=201,
)
def create_rate_limit_policy(
    data: RateLimitPolicyCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = rate_limit_policy_service.create_policy(
        db,
        data=data,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_rate_limit_policy_created",
        entity_type="rate_limit_policy",
        entity_id=str(result.id),
        description=(
            f"Created rate limit policy {result.key}."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get("user-agent"),
    )

    return result


@router.patch(
    "/rate-limits/policies/{policy_id}",
    response_model=RateLimitPolicyResponse,
)
def update_rate_limit_policy(
    policy_id: int,
    data: RateLimitPolicyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = rate_limit_policy_service.update_policy(
        db,
        policy_id=policy_id,
        data=data,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_rate_limit_policy_updated",
        entity_type="rate_limit_policy",
        entity_id=str(result.id),
        description=(
            f"Updated rate limit policy {result.key}."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get("user-agent"),
    )

    return result


@router.post(
    "/rate-limits/policies/{policy_id}/enable",
    response_model=RateLimitPolicyResponse,
)
def enable_rate_limit_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return rate_limit_policy_service.set_enabled(
        db,
        policy_id=policy_id,
        enabled=True,
    )


@router.post(
    "/rate-limits/policies/{policy_id}/disable",
    response_model=RateLimitPolicyResponse,
)
def disable_rate_limit_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return rate_limit_policy_service.set_enabled(
        db,
        policy_id=policy_id,
        enabled=False,
    )


@router.delete(
    "/rate-limits/policies/{policy_id}",
    response_model=SuccessResponse,
)
def delete_rate_limit_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    rate_limit_policy_service.delete_policy(
        db,
        policy_id=policy_id,
    )

    return SuccessResponse(
        message="Rate limit policy deleted successfully.",
    )


@router.post(
    "/rate-limits/policies/seed-defaults",
)
def seed_default_rate_limit_policies(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return (
        default_rate_limit_policies_service
        .seed_defaults(db)
    )