from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.analytics import AnalyticsResponse
from app.services.analytics_service import analytics_service

router = APIRouter()


@router.get("/analytics", response_model=AnalyticsResponse)
def get_analytics(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
    days: int = Query(default=30, ge=1, le=365),
):
    return analytics_service.get_analytics(
        db=db,
        days=days,
    )