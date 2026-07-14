from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.admin_dashboard import AdminDashboardResponse
from app.services.admin_dashboard_service import admin_dashboard_service

router = APIRouter()


@router.get("/dashboard", response_model=AdminDashboardResponse)
def get_admin_dashboard(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return admin_dashboard_service.get_dashboard(db)