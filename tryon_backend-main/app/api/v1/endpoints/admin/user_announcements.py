from fastapi import (
    APIRouter,
    Depends,
    Request,
    status,
)
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import (
    admin_guard,
)
from app.models.user import User
from app.schemas.user_notification import (
    UserAnnouncementCreate,
    UserNotificationCreate,
    UserNotificationResponse,
)
from app.services.audit_entry_service import (
    audit_entry_service,
)
from app.services.user_notification_service import (
    user_notification_service,
)


router = APIRouter()


@router.post(
    "/user-announcements",
    response_model=UserNotificationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user_announcement(
    data: UserAnnouncementCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    notification = (
        user_notification_service.create(
            db,
            data=UserNotificationCreate(
                recipient_user_id=None,
                notification_type=(
                    data.notification_type
                ),
                priority=data.priority,
                source="announcement",
                event_type=(
                    "system_announcement"
                ),
                title=data.title,
                message=data.message,
                action_url=data.action_url,
                action_label=data.action_label,
                image_url=data.image_url,
                metadata=data.metadata,
                is_global=True,
                requires_action=(
                    data.requires_action
                ),
                published_at=(
                    data.published_at
                ),
                expires_at=data.expires_at,
            ),
        )
    )

    result = (
        user_notification_service
        ._response(
            notification,
            None,
        )
    )

    audit_entry_service.safe_record(
        db,
        action="create",
        entity_type="user_announcement",
        entity_id=notification.id,
        actor=current_admin,
        before=None,
        after=result,
        request=request,
        metadata={
            "module": (
                "user_notifications"
            ),
        },
    )

    return result