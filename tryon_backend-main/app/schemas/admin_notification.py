from datetime import datetime
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


class AdminNotificationCreate(BaseModel):
    recipient_user_id: int | None = None

    notification_type: str = Field(
        default="info",
        min_length=2,
        max_length=30,
    )

    priority: str = Field(
        default="normal",
        min_length=2,
        max_length=30,
    )

    source: str = Field(
        default="system",
        min_length=2,
        max_length=60,
    )

    event_type: str | None = Field(
        default=None,
        max_length=150,
    )

    title: str = Field(
        min_length=1,
        max_length=255,
    )

    message: str = Field(
        min_length=1,
        max_length=20000,
    )

    action_url: str | None = Field(
        default=None,
        max_length=2000,
    )

    action_label: str | None = Field(
        default=None,
        max_length=120,
    )

    entity_type: str | None = Field(
        default=None,
        max_length=120,
    )

    entity_id: str | int | None = None

    correlation_id: str | None = Field(
        default=None,
        max_length=128,
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )

    is_global: bool = False
    requires_action: bool = False

    expires_at: datetime | None = None


class AdminNotificationResponse(BaseModel):
    id: int

    recipient_user_id: int | None

    notification_type: str
    priority: str
    source: str
    event_type: str | None

    title: str
    message: str

    action_url: str | None
    action_label: str | None

    entity_type: str | None
    entity_id: str | None

    correlation_id: str | None
    metadata: dict[str, Any]

    is_global: bool
    is_read: bool
    is_archived: bool
    requires_action: bool

    read_at: datetime | None
    archived_at: datetime | None
    expires_at: datetime | None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class AdminNotificationListResponse(BaseModel):
    items: list[AdminNotificationResponse]

    total: int
    unread: int

    skip: int
    limit: int


class AdminNotificationCountResponse(BaseModel):
    total: int
    unread: int
    urgent: int
    requires_action: int


class AdminNotificationMarkReadRequest(BaseModel):
    notification_ids: list[int] = Field(
        min_length=1,
        max_length=1000,
    )


class AdminNotificationBulkActionResponse(BaseModel):
    success: bool
    affected: int


class AdminNotificationArchiveRequest(BaseModel):
    notification_ids: list[int] = Field(
        min_length=1,
        max_length=1000,
    )


class AdminNotificationDeleteRequest(BaseModel):
    notification_ids: list[int] = Field(
        min_length=1,
        max_length=1000,
    )


class AdminNotificationPreferencePreview(BaseModel):
    source: str
    notification_type: str
    priority: str
    delivery_channels: list[str] = Field(
        default_factory=lambda: [
            "backoffice",
        ]
    )