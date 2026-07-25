from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.common.enums import NotificationCategory, NotificationType


class NotificationCreate(BaseModel):
    notification_type: NotificationType = NotificationType.INFO
    category: NotificationCategory = NotificationCategory.SYSTEM
    title: str
    message: str
    metadata_json: str | None = None


class NotificationResponse(BaseModel):
    id: int
    notification_type: NotificationType
    category: NotificationCategory
    title: str
    message: str
    metadata_json: str | None
    is_read: bool
    created_at: datetime
    read_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class NotificationUnreadCountResponse(BaseModel):
    unread_count: int