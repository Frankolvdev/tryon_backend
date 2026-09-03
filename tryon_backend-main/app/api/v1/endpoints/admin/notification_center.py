from datetime import datetime

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
from app.schemas.admin_notification import (
    AdminNotificationArchiveRequest,
    AdminNotificationBulkActionResponse,
    AdminNotificationCountResponse,
    AdminNotificationCreate,
    AdminNotificationListResponse,
    AdminNotificationMarkReadRequest,
    AdminNotificationResponse,
)
from app.services.admin_notification_service import (
    admin_notification_service,
)
from app.services.audit_entry_service import (
    audit_entry_service,
)


router = APIRouter()


@router.get(
    "/notification-center",
    response_model=(
        AdminNotificationListResponse
    ),
)
def list_notifications(
    notification_type: str | None = Query(
        default=None,
    ),
    priority: str | None = Query(
        default=None,
    ),
    source: str | None = Query(
        default=None,
    ),
    event_type: str | None = Query(
        default=None,
    ),
    is_read: bool | None = Query(
        default=None,
    ),
    is_archived: bool | None = Query(
        default=False,
    ),
    requires_action: bool | None = Query(
        default=None,
    ),
    entity_type: str | None = Query(
        default=None,
    ),
    entity_id: str | None = Query(
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
    include_expired: bool = Query(
        default=False,
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
    return (
        admin_notification_service
        .list_for_user(
            db,
            user_id=current_admin.id,
            notification_type=(
                notification_type
            ),
            priority=priority,
            source=source,
            event_type=event_type,
            is_read=is_read,
            is_archived=is_archived,
            requires_action=(
                requires_action
            ),
            entity_type=entity_type,
            entity_id=entity_id,
            search=search,
            created_from=created_from,
            created_to=created_to,
            include_expired=(
                include_expired
            ),
            skip=skip,
            limit=limit,
        )
    )


@router.get(
    "/notification-center/counts",
    response_model=(
        AdminNotificationCountResponse
    ),
)
def get_notification_counts(
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    return (
        admin_notification_service
        .counts(
            db,
            user_id=current_admin.id,
        )
    )


@router.post(
    "/notification-center",
    response_model=(
        AdminNotificationResponse
    ),
)
def create_notification(
    data: AdminNotificationCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    result = (
        admin_notification_service
        .create(
            db,
            data=data,
        )
    )

    audit_entry_service.safe_record(
        db,
        action="create",
        entity_type="admin_notification",
        entity_id=result.id,
        actor=current_admin,
        before=None,
        after=result,
        request=request,
        metadata={
            "module": (
                "notification_center"
            ),
        },
    )

    return result


@router.get(
    "/notification-center/{notification_id}",
    response_model=(
        AdminNotificationResponse
    ),
)
def get_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    return (
        admin_notification_service
        .get_response_for_user(
            db,
            notification_id=(
                notification_id
            ),
            user_id=current_admin.id,
        )
    )


@router.post(
    "/notification-center/"
    "{notification_id}/read",
    response_model=(
        AdminNotificationResponse
    ),
)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    return (
        admin_notification_service
        .mark_read(
            db,
            notification_id=(
                notification_id
            ),
            user_id=current_admin.id,
        )
    )


@router.post(
    "/notification-center/"
    "{notification_id}/unread",
    response_model=(
        AdminNotificationResponse
    ),
)
def mark_notification_unread(
    notification_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    return (
        admin_notification_service
        .mark_unread(
            db,
            notification_id=(
                notification_id
            ),
            user_id=current_admin.id,
        )
    )


@router.post(
    "/notification-center/mark-read",
    response_model=(
        AdminNotificationBulkActionResponse
    ),
)
def mark_notifications_read(
    data: AdminNotificationMarkReadRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    return (
        admin_notification_service
        .mark_many_read(
            db,
            notification_ids=(
                data.notification_ids
            ),
            user_id=current_admin.id,
        )
    )


@router.post(
    "/notification-center/mark-all-read",
    response_model=(
        AdminNotificationBulkActionResponse
    ),
)
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    return (
        admin_notification_service
        .mark_all_read(
            db,
            user_id=current_admin.id,
        )
    )


@router.post(
    "/notification-center/"
    "{notification_id}/archive",
    response_model=(
        AdminNotificationResponse
    ),
)
def archive_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    return (
        admin_notification_service
        .archive(
            db,
            notification_id=(
                notification_id
            ),
            user_id=current_admin.id,
        )
    )


@router.post(
    "/notification-center/archive",
    response_model=(
        AdminNotificationBulkActionResponse
    ),
)
def archive_notifications(
    data: AdminNotificationArchiveRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    return (
        admin_notification_service
        .archive_many(
            db,
            notification_ids=(
                data.notification_ids
            ),
            user_id=current_admin.id,
        )
    )