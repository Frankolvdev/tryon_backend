from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.system_status import SystemStatusResponse, SystemStatusUpdate
from app.services.audit_service import audit_service
from app.services.system_status_service import system_status_service

router = APIRouter()


@router.get("/system-status", response_model=SystemStatusResponse)
def get_admin_system_status(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return system_status_service.get_or_create_status(db)


@router.patch("/system-status", response_model=SystemStatusResponse)
def update_admin_system_status(
    data: SystemStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    status = system_status_service.update_status(
        db=db,
        data=data,
        admin_user=current_admin,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_system_status_updated",
        entity_type="system_status",
        entity_id=str(status.id),
        description="Admin updated system status.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return status