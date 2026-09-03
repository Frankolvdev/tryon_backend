from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.services.audit_service import audit_service
from app.services.default_rbac_service import default_rbac_service

router = APIRouter()


@router.post("/rbac/seed-defaults")
def seed_default_rbac(
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = default_rbac_service.seed_all(db)

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_rbac_seeded",
        entity_type="rbac",
        entity_id=None,
        description="Admin seeded default RBAC roles, permissions and feature permissions.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return {
        "message": "Default RBAC processed successfully.",
        **result,
    }