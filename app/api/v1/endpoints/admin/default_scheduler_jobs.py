from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.services.audit_service import audit_service
from app.services.default_scheduler_jobs_service import default_scheduler_jobs_service

router = APIRouter()


@router.post("/scheduled-jobs/seed-defaults")
def seed_default_scheduled_jobs(
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = default_scheduler_jobs_service.seed_defaults(db)

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_scheduled_jobs_seeded",
        entity_type="scheduled_jobs",
        entity_id=None,
        description="Admin seeded default scheduled jobs.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return {
        "message": "Default scheduled jobs processed successfully.",
        **result,
    }