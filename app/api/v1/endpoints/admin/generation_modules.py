from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.common.generation_module_enums import GenerationExecutionEngine
from app.models.user import User
from app.schemas.generation_module import (
    GenerationModuleCreate,
    GenerationModuleListResponse,
    GenerationModuleResponse,
    GenerationModuleUpdate,
)
from app.services.audit_service import audit_service
from app.services.generation_module_service import generation_module_service

router = APIRouter()


@router.get("/generation-modules", response_model=GenerationModuleListResponse)
def list_generation_modules(
    key: str | None = Query(default=None),
    category: str | None = Query(default=None),
    engine: GenerationExecutionEngine | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return generation_module_service.list_modules(
        db,
        key=key,
        category=category,
        engine=engine.value if engine else None,
        is_active=is_active,
        search=search,
        skip=skip,
        limit=limit,
    )


@router.get("/generation-modules/{module_id}", response_model=GenerationModuleResponse)
def get_generation_module(
    module_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return generation_module_service.get_response(db, module_id=module_id)


@router.post(
    "/generation-modules", response_model=GenerationModuleResponse, status_code=201
)
def create_generation_module(
    data: GenerationModuleCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = generation_module_service.create(
        db, data=data, created_by_user_id=current_admin.id
    )
    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_generation_module_created",
        entity_type="generation_module",
        entity_id=str(result.id),
        description=f"Created generation module {result.key} version {result.version}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return result


@router.patch(
    "/generation-modules/{module_id}", response_model=GenerationModuleResponse
)
def update_generation_module(
    module_id: int,
    data: GenerationModuleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = generation_module_service.update(db, module_id=module_id, data=data)
    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_generation_module_updated",
        entity_type="generation_module",
        entity_id=str(module_id),
        description=f"Updated generation module {module_id}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return result


@router.delete("/generation-modules/{module_id}", status_code=204)
def delete_generation_module(
    module_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    generation_module_service.delete(db, module_id=module_id)
    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_generation_module_deleted",
        entity_type="generation_module",
        entity_id=str(module_id),
        description=f"Deleted generation module {module_id}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return Response(status_code=204)
