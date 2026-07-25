from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.common.enums import SettingCategory
from app.models.user import User
from app.schemas.system_setting import (
    SystemSettingCreate,
    SystemSettingResponse,
    SystemSettingsByCategoryResponse,
    SystemSettingsGroupedResponse,
    SystemSettingUpdate,
)
from app.services.audit_service import audit_service
from app.services.system_setting_service import system_setting_service

router = APIRouter()


@router.get("/system-settings", response_model=list[SystemSettingResponse])
def list_system_settings(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return system_setting_service.list_settings(db)


@router.get(
    "/system-settings/grouped",
    response_model=SystemSettingsGroupedResponse,
)
def list_grouped_system_settings(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return system_setting_service.list_grouped_settings(db)


@router.get(
    "/system-settings/by-category",
    response_model=SystemSettingsByCategoryResponse,
)
def list_system_settings_by_category(
    category: SettingCategory = Query(...),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return system_setting_service.list_settings_by_category(
        db=db,
        category=category,
    )


@router.post("/system-settings", response_model=SystemSettingResponse)
def create_system_setting(
    data: SystemSettingCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    setting = system_setting_service.create_setting(
        db=db,
        data=data,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_system_setting_created",
        entity_type="system_setting",
        entity_id=str(setting.id),
        description=f"Admin created system setting {setting.key}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return setting


@router.patch("/system-settings/{setting_id}", response_model=SystemSettingResponse)
def update_system_setting(
    setting_id: int,
    data: SystemSettingUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    setting = system_setting_service.update_setting(
        db=db,
        setting_id=setting_id,
        data=data,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_system_setting_updated",
        entity_type="system_setting",
        entity_id=str(setting.id),
        description=f"Admin updated system setting {setting.key}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return setting