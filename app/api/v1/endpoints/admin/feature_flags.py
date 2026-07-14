from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.feature_flag import (
    FeatureFlagCreate,
    FeatureFlagResponse,
    FeatureFlagUpdate,
)
from app.services.feature_flag_service import feature_flag_service

router = APIRouter()


@router.get("/feature-flags", response_model=list[FeatureFlagResponse])
def list_feature_flags(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return feature_flag_service.list_flags(db)


@router.post("/feature-flags", response_model=FeatureFlagResponse)
def create_feature_flag(
    data: FeatureFlagCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return feature_flag_service.create_flag(
        db=db,
        data=data,
    )


@router.patch("/feature-flags/{flag_id}", response_model=FeatureFlagResponse)
def update_feature_flag(
    flag_id: int,
    data: FeatureFlagUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return feature_flag_service.update_flag(
        db=db,
        flag_id=flag_id,
        data=data,
    )