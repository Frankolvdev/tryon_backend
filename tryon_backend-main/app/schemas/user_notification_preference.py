from datetime import datetime, time

from pydantic import BaseModel, Field


class UserNotificationPreferenceUpdate(BaseModel):
    in_app_enabled: bool = True
    email_enabled: bool = True
    web_push_enabled: bool = True
    marketing_enabled: bool = False

    tryon_notifications_enabled: bool = True
    billing_notifications_enabled: bool = True
    token_notifications_enabled: bool = True
    subscription_notifications_enabled: bool = True
    support_notifications_enabled: bool = True
    security_notifications_enabled: bool = True
    announcement_notifications_enabled: bool = True

    minimum_priority: str = Field(
        default="low",
        max_length=30,
    )

    email_minimum_priority: str = Field(
        default="normal",
        max_length=30,
    )

    web_push_minimum_priority: str = Field(
        default="normal",
        max_length=30,
    )

    quiet_hours_enabled: bool = False
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None

    timezone: str = Field(
        default="America/Mexico_City",
        min_length=1,
        max_length=100,
    )

    allow_urgent_during_quiet_hours: bool = True

    disabled_event_types: list[str] = Field(
        default_factory=list,
        max_length=200,
    )


class UserNotificationPreferenceResponse(BaseModel):
    id: int
    user_id: int

    in_app_enabled: bool
    email_enabled: bool
    web_push_enabled: bool
    marketing_enabled: bool

    tryon_notifications_enabled: bool
    billing_notifications_enabled: bool
    token_notifications_enabled: bool
    subscription_notifications_enabled: bool
    support_notifications_enabled: bool
    security_notifications_enabled: bool
    announcement_notifications_enabled: bool

    minimum_priority: str
    email_minimum_priority: str
    web_push_minimum_priority: str

    quiet_hours_enabled: bool
    quiet_hours_start: time | None
    quiet_hours_end: time | None

    timezone: str
    allow_urgent_during_quiet_hours: bool

    disabled_event_types: list[str]

    created_at: datetime
    updated_at: datetime


class UserPushSubscriptionCreate(BaseModel):
    endpoint: str = Field(
        min_length=10,
        max_length=10000,
    )

    p256dh_key: str = Field(
        min_length=10,
        max_length=5000,
    )

    auth_key: str = Field(
        min_length=5,
        max_length=5000,
    )

    device_name: str | None = Field(
        default=None,
        max_length=255,
    )


class UserPushSubscriptionResponse(BaseModel):
    id: int
    device_name: str | None
    is_active: bool

    failure_count: int

    last_used_at: datetime | None
    last_success_at: datetime | None
    last_failure_at: datetime | None

    created_at: datetime
    updated_at: datetime


class UserNotificationDeliveryTestRequest(BaseModel):
    channel: str = Field(
        pattern="^(email|web_push)$",
    )


class UserNotificationDeliveryTestResponse(BaseModel):
    success: bool
    channel: str
    message: str