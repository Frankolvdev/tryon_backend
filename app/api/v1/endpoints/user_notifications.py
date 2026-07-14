from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.auth_guard import (
    auth_guard,
)
from app.models.user import User
from app.schemas.user_notification import (
    UserNotificationBulkRequest,
    UserNotificationBulkResponse,
    UserNotificationCountResponse,
    UserNotificationListResponse,
    UserNotificationResponse,
)
from app.schemas.user_notification_preference import (
    UserNotificationPreferenceResponse,
    UserNotificationPreferenceUpdate,
    UserPushSubscriptionCreate,
    UserPushSubscriptionResponse,
)
from app.services.user_notification_preference_service import (
    user_notification_preference_service,
)
from app.services.user_notification_service import (
    user_notification_service,
)


router = APIRouter()


@router.get(
    "/preferences",
    response_model=UserNotificationPreferenceResponse,
)
def get_user_notification_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return (
        user_notification_preference_service
        .get_response(
            db,
            user_id=current_user.id,
        )
    )


@router.put(
    "/preferences",
    response_model=UserNotificationPreferenceResponse,
)
def update_user_notification_preferences(
    data: UserNotificationPreferenceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return (
        user_notification_preference_service
        .update(
            db,
            user_id=current_user.id,
            data=data,
        )
    )


@router.post(
    "/push-subscriptions",
    response_model=UserPushSubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user_push_subscription(
    data: UserPushSubscriptionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return (
        user_notification_preference_service
        .register_push_subscription(
            db,
            user_id=current_user.id,
            data=data,
            user_agent=request.headers.get(
                "user-agent"
            ),
        )
    )


@router.get(
    "/push-subscriptions",
    response_model=list[
        UserPushSubscriptionResponse
    ],
)
def list_user_push_subscriptions(
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return (
        user_notification_preference_service
        .list_push_subscriptions(
            db,
            user_id=current_user.id,
        )
    )


@router.delete(
    "/push-subscriptions/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_user_push_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    (
        user_notification_preference_service
        .remove_push_subscription(
            db,
            user_id=current_user.id,
            subscription_id=subscription_id,
        )
    )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )


@router.get(
    "",
    response_model=UserNotificationListResponse,
)
def list_user_notifications(
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
    current_user: User = Depends(auth_guard),
):
    return user_notification_service.list_for_user(
        db,
        user_id=current_user.id,
        notification_type=notification_type,
        priority=priority,
        source=source,
        event_type=event_type,
        is_read=is_read,
        is_archived=is_archived,
        requires_action=requires_action,
        search=search,
        created_from=created_from,
        created_to=created_to,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/counts",
    response_model=UserNotificationCountResponse,
)
def get_user_notification_counts(
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return user_notification_service.counts(
        db,
        user_id=current_user.id,
    )


@router.post(
    "/mark-read",
    response_model=UserNotificationBulkResponse,
)
def mark_user_notifications_read(
    data: UserNotificationBulkRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return (
        user_notification_service
        .mark_many_read(
            db,
            user_id=current_user.id,
            notification_ids=(
                data.notification_ids
            ),
        )
    )


@router.post(
    "/mark-all-read",
    response_model=UserNotificationBulkResponse,
)
def mark_all_user_notifications_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return (
        user_notification_service
        .mark_all_read(
            db,
            user_id=current_user.id,
        )
    )


@router.get(
    "/{notification_id}",
    response_model=UserNotificationResponse,
)
def get_user_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return (
        user_notification_service
        .get_for_user(
            db,
            user_id=current_user.id,
            notification_id=notification_id,
        )
    )


@router.post(
    "/{notification_id}/read",
    response_model=UserNotificationResponse,
)
def mark_user_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return user_notification_service.mark_read(
        db,
        user_id=current_user.id,
        notification_id=notification_id,
    )


@router.post(
    "/{notification_id}/unread",
    response_model=UserNotificationResponse,
)
def mark_user_notification_unread(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return user_notification_service.mark_unread(
        db,
        user_id=current_user.id,
        notification_id=notification_id,
    )


@router.post(
    "/{notification_id}/archive",
    response_model=UserNotificationResponse,
)
def archive_user_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return user_notification_service.archive(
        db,
        user_id=current_user.id,
        notification_id=notification_id,
    )