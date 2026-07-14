from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.audit import AuditLogResponse
from app.services.audit_service import audit_service

router = APIRouter()


@router.get("/audit-logs", response_model=list[AuditLogResponse])
def list_audit_logs(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
):
    return audit_service.list_logs(
        db=db,
        skip=skip,
        limit=limit,
    )