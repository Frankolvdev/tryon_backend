from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.services.audit_service import audit_service
from app.services.default_settings_service import default_settings_service

router = APIRouter()


@router.post("/system-settings/seed-defaults")
def seed_default_system_settings(
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = default_settings_service.seed_defaults(db)

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_system_settings_seeded",
        entity_type="system_settings",
        entity_id=None,
        description="Admin seeded default system settings.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return {
        "message": "Default system settings processed successfully.",
        **result,
    }