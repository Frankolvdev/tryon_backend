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
from app.api.v1.guards.admin_guard import (
    admin_guard,
)
from app.models.user import User
from app.schemas.admin_notification_delivery import (
    AdminNotificationChannelTestRequest,
    AdminNotificationChannelTestResponse,
    AdminNotificationDeliveryListResponse,
    AdminNotificationRetryResponse,
)
from app.schemas.admin_notification_preference import (
    AdminNotificationChannelCreate,
    AdminNotificationChannelResponse,
    AdminNotificationChannelUpdate,
    AdminNotificationPreferenceResponse,
    AdminNotificationPreferenceUpdate,
    AdminNotificationSettingsResponse,
    NotificationRoutingPreviewRequest,
    NotificationRoutingPreviewResponse,
)
from app.services.admin_notification_delivery_service import (
    admin_notification_delivery_service,
)
from app.services.admin_notification_preference_service import (
    admin_notification_preference_service,
)
from app.services.audit_entry_service import (
    audit_entry_service,
)


router = APIRouter()


@router.get(
    "/notification-preferences",
    response_model=AdminNotificationSettingsResponse,
)
def get_notification_preferences(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return (
        admin_notification_preference_service
        .get_settings(
            db,
            user_id=current_admin.id,
        )
    )


@router.put(
    "/notification-preferences",
    response_model=(
        AdminNotificationPreferenceResponse
    ),
)
def update_notification_preferences(
    data: AdminNotificationPreferenceUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    before = (
        admin_notification_preference_service
        .get_settings(
            db,
            user_id=current_admin.id,
        )
        .preference
    )

    result = (
        admin_notification_preference_service
        .update_preference(
            db,
            user_id=current_admin.id,
            data=data,
        )
    )

    audit_entry_service.safe_record(
        db,
        action="update",
        entity_type=(
            "admin_notification_preference"
        ),
        entity_id=result.id,
        actor=current_admin,
        before=before,
        after=result,
        request=request,
        metadata={
            "module": "notification_preferences",
        },
        is_restorable=True,
    )

    return result


@router.post(
    "/notification-preferences/channels",
    response_model=(
        AdminNotificationChannelResponse
    ),
    status_code=status.HTTP_201_CREATED,
)
def create_notification_channel(
    data: AdminNotificationChannelCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = (
        admin_notification_preference_service
        .create_channel(
            db,
            user_id=current_admin.id,
            data=data,
        )
    )

    audit_entry_service.safe_record(
        db,
        action="create",
        entity_type=(
            "admin_notification_channel"
        ),
        entity_id=result.id,
        actor=current_admin,
        before=None,
        after=result,
        request=request,
        metadata={
            "channel_type": result.channel_type,
        },
    )

    return result


@router.put(
    "/notification-preferences/channels/{channel_id}",
    response_model=(
        AdminNotificationChannelResponse
    ),
)
def update_notification_channel(
    channel_id: int,
    data: AdminNotificationChannelUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    settings_before = (
        admin_notification_preference_service
        .get_settings(
            db,
            user_id=current_admin.id,
        )
    )

    before = next(
        (
            channel
            for channel in settings_before.channels
            if channel.id == channel_id
        ),
        None,
    )

    result = (
        admin_notification_preference_service
        .update_channel(
            db,
            user_id=current_admin.id,
            channel_id=channel_id,
            data=data,
        )
    )

    audit_entry_service.safe_record(
        db,
        action="update",
        entity_type=(
            "admin_notification_channel"
        ),
        entity_id=result.id,
        actor=current_admin,
        before=before,
        after=result,
        request=request,
        metadata={
            "channel_type": result.channel_type,
        },
        is_restorable=True,
    )

    return result


@router.delete(
    "/notification-preferences/channels/{channel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_notification_channel(
    channel_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    settings_before = (
        admin_notification_preference_service
        .get_settings(
            db,
            user_id=current_admin.id,
        )
    )

    before = next(
        (
            channel
            for channel in settings_before.channels
            if channel.id == channel_id
        ),
        None,
    )

    (
        admin_notification_preference_service
        .delete_channel(
            db,
            user_id=current_admin.id,
            channel_id=channel_id,
        )
    )

    audit_entry_service.safe_record(
        db,
        action="delete",
        entity_type=(
            "admin_notification_channel"
        ),
        entity_id=channel_id,
        actor=current_admin,
        before=before,
        after=None,
        request=request,
        metadata={
            "module": "notification_preferences",
        },
    )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )


@router.post(
    "/notification-preferences/routing-preview",
    response_model=(
        NotificationRoutingPreviewResponse
    ),
)
def preview_notification_routing(
    data: NotificationRoutingPreviewRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return (
        admin_notification_preference_service
        .preview_routing(
            db,
            user_id=current_admin.id,
            data=data,
        )
    )


@router.post(
    "/notification-preferences/channels/"
    "{channel_id}/test",
    response_model=(
        AdminNotificationChannelTestResponse
    ),
)
def test_notification_channel(
    channel_id: int,
    data: AdminNotificationChannelTestRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    delivery = (
        admin_notification_delivery_service
        .test_channel(
            db,
            user_id=current_admin.id,
            channel_id=channel_id,
            title=data.title,
            message=data.message,
        )
    )

    audit_entry_service.safe_record(
        db,
        action="execute",
        entity_type=(
            "admin_notification_channel_test"
        ),
        entity_id=channel_id,
        actor=current_admin,
        before=None,
        after={
            "delivery_id": delivery.id,
            "status": delivery.status,
            "channel_type": (
                delivery.channel_type
            ),
        },
        request=request,
        success=(
            delivery.status == "delivered"
        ),
        metadata={
            "module": "notification_delivery",
        },
    )

    return AdminNotificationChannelTestResponse(
        success=(
            delivery.status == "delivered"
        ),
        channel_id=channel_id,
        channel_type=delivery.channel_type,
        delivery=delivery,
        message=(
            "Channel test delivered successfully."
            if delivery.status == "delivered"
            else (
                "Channel test did not succeed. "
                "Review the delivery error."
            )
        ),
    )


@router.get(
    "/notification-center/{notification_id}/deliveries",
    response_model=(
        AdminNotificationDeliveryListResponse
    ),
)
def list_notification_deliveries(
    notification_id: int,
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
    current_admin: User = Depends(admin_guard),
):
    return (
        admin_notification_delivery_service
        .list_for_notification(
            db,
            notification_id=notification_id,
            skip=skip,
            limit=limit,
        )
    )


@router.post(
    "/notification-deliveries/{delivery_id}/retry",
    response_model=AdminNotificationRetryResponse,
)
def retry_notification_delivery(
    delivery_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    delivery = (
        admin_notification_delivery_service
        .retry_delivery(
            db,
            delivery_id=delivery_id,
        )
    )

    audit_entry_service.safe_record(
        db,
        action="retry",
        entity_type=(
            "admin_notification_delivery"
        ),
        entity_id=delivery_id,
        actor=current_admin,
        before=None,
        after={
            "status": delivery.status,
            "attempt_count": (
                delivery.attempt_count
            ),
        },
        request=request,
        success=(
            delivery.status == "delivered"
        ),
    )

    return AdminNotificationRetryResponse(
        success=(
            delivery.status == "delivered"
        ),
        delivery_id=delivery.id,
        status=delivery.status,
        attempt_count=delivery.attempt_count,
        message=(
            "Delivery succeeded."
            if delivery.status == "delivered"
            else (
                "Delivery failed and may be "
                "scheduled for another retry."
            )
        ),
    )