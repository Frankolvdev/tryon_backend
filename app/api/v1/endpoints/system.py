from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.schemas.system_setting import (
    PublicFrontendConfigResponse,
    PublicSystemSettingResponse,
)
from app.schemas.system_status import PublicSystemStatusResponse
from app.services.system_setting_service import system_setting_service
from app.services.system_status_service import system_status_service

router = APIRouter()


@router.get("/status", response_model=PublicSystemStatusResponse)
def get_system_status(
    db: Session = Depends(get_db),
):
    status = system_status_service.get_public_status(db)

    return PublicSystemStatusResponse(
        maintenance_mode=status.maintenance_mode,
        registration_enabled=status.registration_enabled,
        tryon_enabled=status.tryon_enabled,
        public_message=status.public_message,
    )


@router.get("/settings/public", response_model=list[PublicSystemSettingResponse])
def get_public_system_settings(
    db: Session = Depends(get_db),
):
    return system_setting_service.list_public_settings(db)


@router.get("/config", response_model=PublicFrontendConfigResponse)
def get_public_frontend_config(
    db: Session = Depends(get_db),
):
    return system_setting_service.get_public_frontend_config(db)