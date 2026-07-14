from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
)
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import (
    admin_guard,
)
from app.models.user import User
from app.schemas.audit_restoration import (
    AuditRestorePreviewResponse,
    AuditRestoreRequest,
    AuditRestoreResponse,
)
from app.services.audit_restore_registry_service import (
    audit_restore_registry_service,
)
from app.services.audit_restoration_service import (
    audit_restoration_service,
)


router = APIRouter()


@router.get(
    "/audit-restorations/entity-types",
    response_model=list[str],
)
def list_restorable_entity_types(
    current_admin: User = Depends(
        admin_guard
    ),
):
    return (
        audit_restore_registry_service
        .list_entity_types()
    )


@router.get(
    "/audit-entries/{audit_entry_id}/"
    "restore-preview",
    response_model=(
        AuditRestorePreviewResponse
    ),
)
def preview_audit_restoration(
    audit_entry_id: int,
    restore_null_values: bool = Query(
        default=True,
    ),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    return audit_restoration_service.preview(
        db,
        audit_entry_id=audit_entry_id,
        restore_null_values=(
            restore_null_values
        ),
    )


@router.post(
    "/audit-entries/{audit_entry_id}/restore",
    response_model=AuditRestoreResponse,
)
def restore_audited_version(
    audit_entry_id: int,
    data: AuditRestoreRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    return audit_restoration_service.restore(
        db,
        audit_entry_id=audit_entry_id,
        data=data,
        current_admin=current_admin,
        request=request,
    )