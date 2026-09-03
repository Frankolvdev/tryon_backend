from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.runpod import (
    RunPodConfigCreate,
    RunPodConfigResponse,
    RunPodConfigUpdate,
)
from app.services.runpod_config_service import runpod_config_service

router = APIRouter()


@router.get("/runpod-configs", response_model=list[RunPodConfigResponse])
def list_runpod_configs(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return runpod_config_service.list_configs(db)


@router.post("/runpod-configs", response_model=RunPodConfigResponse)
def create_runpod_config(
    data: RunPodConfigCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return runpod_config_service.create_config(
        db=db,
        data=data,
    )


@router.patch("/runpod-configs/{config_id}", response_model=RunPodConfigResponse)
def update_runpod_config(
    config_id: int,
    data: RunPodConfigUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return runpod_config_service.update_config(
        db=db,
        config_id=config_id,
        data=data,
    )