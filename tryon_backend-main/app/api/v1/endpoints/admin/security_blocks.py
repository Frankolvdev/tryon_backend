from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import (
    admin_guard,
)
from app.common.rate_limit_enums import (
    BlockTargetType,
)
from app.models.user import User
from app.schemas.rate_limit import (
    SecurityBlockCreate,
    SecurityBlockListResponse,
    SecurityBlockResponse,
)
from app.services.audit_service import (
    audit_service,
)
from app.services.security_block_service import (
    security_block_service,
)

router = APIRouter()


@router.get(
    "/security-blocks",
    response_model=SecurityBlockListResponse,
)
def list_security_blocks(
    target_type: BlockTargetType | None = Query(
        default=None
    ),
    is_active: bool | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(
        default=100,
        ge=1,
        le=200,
    ),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return security_block_service.list_blocks(
        db,
        target_type=target_type,
        is_active=is_active,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/security-blocks/{block_id}",
    response_model=SecurityBlockResponse,
)
def get_security_block(
    block_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return security_block_service.get_response(
        db,
        block_id=block_id,
    )


@router.post(
    "/security-blocks",
    response_model=SecurityBlockResponse,
    status_code=201,
)
def create_security_block(
    data: SecurityBlockCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = security_block_service.create_block(
        db,
        data=data,
        created_by_user_id=current_admin.id,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_security_block_created",
        entity_type="security_block",
        entity_id=str(result.id),
        description=(
            f"Created security block for "
            f"{result.target_type}:{result.target_value}."
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
    "/security-blocks/{block_id}/deactivate",
    response_model=SecurityBlockResponse,
)
def deactivate_security_block(
    block_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = (
        security_block_service.deactivate_block(
            db,
            block_id=block_id,
        )
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_security_block_deactivated",
        entity_type="security_block",
        entity_id=str(block_id),
        description=(
            f"Deactivated security block {block_id}."
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
    "/security-blocks/{block_id}/reactivate",
    response_model=SecurityBlockResponse,
)
def reactivate_security_block(
    block_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = (
        security_block_service.reactivate_block(
            db,
            block_id=block_id,
        )
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_security_block_reactivated",
        entity_type="security_block",
        entity_id=str(block_id),
        description=(
            f"Reactivated security block {block_id}."
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