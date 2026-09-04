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
from pydantic import BaseModel, Field
from fastapi import HTTPException
from app.services.generation_data_reset_service import generation_data_reset_service


class GenerationResetRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=100)
    delete_storage_files: bool = True
    cancel_stripe_subscriptions: bool = False
    refund_stripe_payments: bool = False


@router.get("/maintenance/generation-reset/preview")
def preview_generation_reset(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return generation_data_reset_service.preview(db)


@router.post("/maintenance/generation-reset")
def reset_generation_data(
    data: GenerationResetRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    try:
        result = generation_data_reset_service.execute(
            db, confirmation=data.confirmation, delete_storage_files=data.delete_storage_files,
            cancel_stripe_subscriptions=data.cancel_stripe_subscriptions,
            refund_stripe_payments=data.refund_stripe_payments,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit_service.create_log(
        db, actor_user_id=current_admin.id, action="admin_generation_data_reset",
        entity_type="system_maintenance", entity_id=None,
        description="Admin reset end-user test activity while preserving accounts and platform/admin configuration.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return result
