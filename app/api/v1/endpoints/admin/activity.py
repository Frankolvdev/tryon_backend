from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.activity import ActivityLogResponse
from app.services.activity_service import activity_service

router = APIRouter()


@router.get("/activity-logs", response_model=list[ActivityLogResponse])
def list_activity_logs(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
):
    return activity_service.list_logs(
        db=db,
        skip=skip,
        limit=limit,
    )


@router.get("/users/{user_id}/activity-logs", response_model=list[ActivityLogResponse])
def list_user_activity_logs(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
):
    return activity_service.list_user_logs(
        db=db,
        user_id=user_id,
        skip=skip,
        limit=limit,
    )