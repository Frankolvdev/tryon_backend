from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
)
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import (
    admin_guard,
)
from app.models.user import User
from app.schemas.audit_entry import (
    AuditDiffResponse,
    AuditEntityHistoryResponse,
    AuditEntryListResponse,
    AuditEntryResponse,
    AuditSummaryResponse,
)
from app.schemas.audit_export import (
    AuditExportRequest,
)
from app.services.audit_entry_service import (
    audit_entry_service,
)
from app.services.audit_export_service import (
    audit_export_service,
)
from app.services.audit_service import (
    audit_service,
)


router = APIRouter()


@router.get(
    "/audit-entries",
    response_model=AuditEntryListResponse,
)
def list_audit_entries(
    actor_user_id: int | None = Query(
        default=None,
    ),
    actor_email: str | None = Query(
        default=None,
    ),
    actor_type: str | None = Query(
        default=None,
    ),
    action: str | None = Query(
        default=None,
    ),
    entity_type: str | None = Query(
        default=None,
    ),
    entity_id: str | None = Query(
        default=None,
    ),
    success: bool | None = Query(
        default=None,
    ),
    correlation_id: str | None = Query(
        default=None,
    ),
    request_id: str | None = Query(
        default=None,
    ),
    is_restorable: bool | None = Query(
        default=None,
    ),
    search: str | None = Query(
        default=None,
    ),
    created_from: datetime | None = Query(
        default=None,
    ),
    created_to: datetime | None = Query(
        default=None,
    ),
    skip: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    return audit_entry_service.list_entries(
        db,
        actor_user_id=actor_user_id,
        actor_email=actor_email,
        actor_type=actor_type,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        success=success,
        correlation_id=correlation_id,
        request_id=request_id,
        is_restorable=is_restorable,
        search=search,
        created_from=created_from,
        created_to=created_to,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/audit-entries/timeline",
    response_model=AuditEntryListResponse,
)
def get_audit_timeline(
    actor_type: str | None = Query(
        default=None,
    ),
    action: str | None = Query(
        default=None,
    ),
    entity_type: str | None = Query(
        default=None,
    ),
    success: bool | None = Query(
        default=None,
    ),
    created_from: datetime | None = Query(
        default=None,
    ),
    created_to: datetime | None = Query(
        default=None,
    ),
    skip: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    return audit_entry_service.list_entries(
        db,
        actor_type=actor_type,
        action=action,
        entity_type=entity_type,
        success=success,
        created_from=created_from,
        created_to=created_to,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/audit-entries/summary",
    response_model=AuditSummaryResponse,
)
def get_audit_summary(
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    return audit_entry_service.summary(db)


@router.post(
    "/audit-entries/export/json",
)
def export_audit_entries_json(
    data: AuditExportRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    content, metadata = (
        audit_export_service.export_json(
            db,
            filters=data,
        )
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_audit_export_json",
        entity_type="audit_entry",
        entity_id=None,
        description=(
            "Exported "
            f"{metadata.exported_records} "
            "advanced audit entries as JSON."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return Response(
        content=content,
        media_type=(
            "application/json; "
            "charset=utf-8"
        ),
        headers={
            "Content-Disposition": (
                "attachment; "
                f'filename="{metadata.filename}"'
            ),
            "X-Exported-Records": str(
                metadata.exported_records
            ),
        },
    )


@router.post(
    "/audit-entries/export/csv",
)
def export_audit_entries_csv(
    data: AuditExportRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    content, metadata = (
        audit_export_service.export_csv(
            db,
            filters=data,
        )
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_audit_export_csv",
        entity_type="audit_entry",
        entity_id=None,
        description=(
            "Exported "
            f"{metadata.exported_records} "
            "advanced audit entries as CSV."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return Response(
        content=content,
        media_type=(
            "text/csv; charset=utf-8"
        ),
        headers={
            "Content-Disposition": (
                "attachment; "
                f'filename="{metadata.filename}"'
            ),
            "X-Exported-Records": str(
                metadata.exported_records
            ),
        },
    )


@router.get(
    "/audit-entries/entity/"
    "{entity_type}/{entity_id}",
    response_model=(
        AuditEntityHistoryResponse
    ),
)
def get_entity_audit_history(
    entity_type: str,
    entity_id: str,
    limit: int = Query(
        default=500,
        ge=1,
        le=5000,
    ),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    return audit_entry_service.entity_history(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
    )


@router.get(
    "/audit-entries/{entry_id}/diff",
    response_model=AuditDiffResponse,
)
def get_audit_entry_diff(
    entry_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    return audit_entry_service.get_diff(
        db,
        entry_id=entry_id,
    )


@router.get(
    "/audit-entries/{entry_id}",
    response_model=AuditEntryResponse,
)
def get_audit_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    return audit_entry_service.get_response(
        db,
        entry_id=entry_id,
    )