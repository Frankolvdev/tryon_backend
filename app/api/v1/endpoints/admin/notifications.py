from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.common.responses import SuccessResponse
from app.models.user import User
from app.schemas.notification import (
    NotificationCreate,
    NotificationResponse,
    NotificationUnreadCountResponse,
)
from app.services.notification_service import notification_service

router = APIRouter()


@router.get("/notifications", response_model=list[NotificationResponse])
def list_notifications(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
):
    return notification_service.list_notifications(
        db=db,
        skip=skip,
        limit=limit,
    )


@router.get("/notifications/unread", response_model=list[NotificationResponse])
def list_unread_notifications(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
):
    return notification_service.list_unread(
        db=db,
        skip=skip,
        limit=limit,
    )


@router.get("/notifications/unread-count", response_model=NotificationUnreadCountResponse)
def count_unread_notifications(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return NotificationUnreadCountResponse(
        unread_count=notification_service.count_unread(db),
    )


@router.post("/notifications", response_model=NotificationResponse)
def create_notification(
    data: NotificationCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return notification_service.create_notification(
        db=db,
        data=data,
    )


@router.patch("/notifications/{notification_id}/read", response_model=NotificationResponse)
def mark_notification_as_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return notification_service.mark_as_read(
        db=db,
        notification_id=notification_id,
    )


@router.patch("/notifications/read-all", response_model=SuccessResponse)
def mark_all_notifications_as_read(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    notification_service.mark_all_as_read(db)
    return SuccessResponse(message="All notifications marked as read.")


@router.delete("/notifications/{notification_id}", response_model=SuccessResponse)
def delete_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    notification_service.delete_notification(
        db=db,
        notification_id=notification_id,
    )

    return SuccessResponse(message="Notification deleted successfully.")


@router.delete("/notifications", response_model=SuccessResponse)
def clear_notifications(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    notification_service.clear_all(db)
    return SuccessResponse(message="Notifications cleared successfully.")