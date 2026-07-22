from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.ai_providers import AiExecutionModeUpdate, AiProvidersOverview
from app.schemas.ai_engine_settings import AiEngineSettingsResponse, AiEngineSettingsUpdate
from app.services.ai_provider_orchestration_service import ai_provider_orchestration_service
from app.services.ai_engine_settings_service import ai_engine_settings_service

router = APIRouter()


@router.get("/ai-providers/overview", response_model=AiProvidersOverview)
def get_ai_providers_overview(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return ai_provider_orchestration_service.overview(db)


@router.patch("/ai-providers/execution-mode", response_model=AiProvidersOverview)
def update_ai_execution_mode(
    data: AiExecutionModeUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return ai_provider_orchestration_service.set_execution_mode(
        db,
        execution_mode=data.execution_mode,
    )


@router.get("/ai-providers/engine-settings", response_model=AiEngineSettingsResponse)
def get_ai_engine_settings(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return ai_engine_settings_service.get(db)


@router.put("/ai-providers/engine-settings", response_model=AiEngineSettingsResponse)
def update_ai_engine_settings(
    data: AiEngineSettingsUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return ai_engine_settings_service.update(db, data)
