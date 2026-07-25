from datetime import datetime
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


class AdminNotificationDeliveryResponse(BaseModel):
    id: int

    notification_id: int
    channel_id: int | None
    recipient_user_id: int | None

    channel_type: str
    destination: str | None

    status: str

    attempt_count: int
    max_attempts: int

    provider_message_id: str | None
    provider_status_code: int | None

    error_type: str | None
    error_message: str | None

    provider_response: dict[str, Any]

    scheduled_at: datetime | None
    processing_started_at: datetime | None
    delivered_at: datetime | None
    failed_at: datetime | None
    next_retry_at: datetime | None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class AdminNotificationDeliveryListResponse(BaseModel):
    items: list[
        AdminNotificationDeliveryResponse
    ]

    total: int
    skip: int
    limit: int


class AdminNotificationChannelTestRequest(BaseModel):
    title: str = Field(
        default="Try-On notification test",
        min_length=1,
        max_length=255,
    )

    message: str = Field(
        default=(
            "This is a test notification from the "
            "AI Virtual Try-On Platform."
        ),
        min_length=1,
        max_length=10000,
    )


class AdminNotificationChannelTestResponse(BaseModel):
    success: bool
    channel_id: int
    channel_type: str

    delivery: (
        AdminNotificationDeliveryResponse | None
    ) = None

    message: str


class AdminNotificationRetryResponse(BaseModel):
    success: bool
    delivery_id: int
    status: str
    attempt_count: int
    message: str