from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.common.responses import SuccessResponse
from app.models.user import User
from app.schemas.api_key import (
    ApiKeyCreate,
    ApiKeyCreateResponse,
    ApiKeyResponse,
    ApiKeyUpdate,
)
from app.services.api_key_service import api_key_service
from app.services.audit_service import audit_service

router = APIRouter()


@router.get("/api-keys", response_model=list[ApiKeyResponse])
def list_api_keys(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
):
    return api_key_service.list_api_keys(
        db=db,
        skip=skip,
        limit=limit,
    )


@router.get("/users/{user_id}/api-keys", response_model=list[ApiKeyResponse])
def list_user_api_keys(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
):
    return api_key_service.list_user_api_keys(
        db=db,
        user_id=user_id,
        skip=skip,
        limit=limit,
    )


@router.post("/api-keys", response_model=ApiKeyCreateResponse)
def create_api_key(
    data: ApiKeyCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = api_key_service.create_api_key(
        db=db,
        data=data,
        created_by_user=current_admin,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_api_key_created",
        entity_type="api_key",
        entity_id=str(result.record.id),
        description=f"Admin created API key {result.record.name}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return result


@router.patch("/api-keys/{api_key_id}", response_model=ApiKeyResponse)
def update_api_key(
    api_key_id: int,
    data: ApiKeyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = api_key_service.update_api_key(
        db=db,
        api_key_id=api_key_id,
        data=data,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_api_key_updated",
        entity_type="api_key",
        entity_id=str(result.id),
        description=f"Admin updated API key {result.name}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return result


@router.post("/api-keys/{api_key_id}/revoke", response_model=SuccessResponse)
def revoke_api_key(
    api_key_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    api_key_service.revoke_api_key(
        db=db,
        api_key_id=api_key_id,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_api_key_revoked",
        entity_type="api_key",
        entity_id=str(api_key_id),
        description="Admin revoked API key.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return SuccessResponse(message="API key revoked successfully.")