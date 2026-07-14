from datetime import datetime
from typing import Any

from pydantic import (
    BaseModel,
    Field,
)


class UserNotificationCreate(BaseModel):
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

    image_url: str | None = Field(
        default=None,
        max_length=2000,
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )

    is_global: bool = False
    requires_action: bool = False

    published_at: datetime | None = None
    expires_at: datetime | None = None


class UserNotificationResponse(BaseModel):
    id: int

    notification_type: str
    priority: str
    source: str
    event_type: str | None

    title: str
    message: str

    action_url: str | None
    action_label: str | None
    image_url: str | None

    entity_type: str | None
    entity_id: str | None

    metadata: dict[str, Any]

    is_global: bool
    requires_action: bool

    is_read: bool
    is_archived: bool

    read_at: datetime | None
    archived_at: datetime | None

    published_at: datetime | None
    expires_at: datetime | None

    created_at: datetime


class UserNotificationListResponse(BaseModel):
    items: list[UserNotificationResponse]

    total: int
    unread: int

    skip: int
    limit: int


class UserNotificationCountResponse(BaseModel):
    total: int
    unread: int
    high_priority: int
    requires_action: int


class UserNotificationBulkRequest(BaseModel):
    notification_ids: list[int] = Field(
        min_length=1,
        max_length=1000,
    )


class UserNotificationBulkResponse(BaseModel):
    success: bool
    affected: int


class UserAnnouncementCreate(BaseModel):
    notification_type: str = Field(
        default="info",
        max_length=30,
    )

    priority: str = Field(
        default="normal",
        max_length=30,
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

    image_url: str | None = Field(
        default=None,
        max_length=2000,
    )

    requires_action: bool = False

    published_at: datetime | None = None
    expires_at: datetime | None = None

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )