from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.monitoring import MonitoringResponse
from app.services.monitoring_service import monitoring_service

router = APIRouter()


@router.get("/monitoring", response_model=MonitoringResponse)
def get_monitoring_status(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return monitoring_service.get_monitoring_status(db)