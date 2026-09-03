from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.common.enums import (
    WebhookDeliveryStatus,
    WebhookEndpointStatus,
    WebhookEventStatus,
)


class WebhookEndpointCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    url: HttpUrl
    subscribed_events: list[str] = []
    description: str | None = None


class WebhookEndpointUpdate(BaseModel):
    name: str | None = None
    url: HttpUrl | None = None
    subscribed_events: list[str] | None = None
    description: str | None = None
    is_active: bool | None = None
    status: WebhookEndpointStatus | None = None


class WebhookEndpointResponse(BaseModel):
    id: int
    name: str
    url: str
    subscribed_events: list[str]
    status: WebhookEndpointStatus
    is_active: bool
    created_by_user_id: int | None
    description: str | None
    last_success_at: datetime | None
    last_failure_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WebhookEndpointCreateResponse(BaseModel):
    endpoint: WebhookEndpointResponse
    signing_secret: str
    warning: str = "Copy this signing secret now. It will not be shown again."


class WebhookEventCreate(BaseModel):
    event_type: str = Field(min_length=3, max_length=255)
    source: str = Field(default="system", min_length=2, max_length=100)
    entity_type: str | None = None
    entity_id: str | None = None
    payload: dict[str, Any] = {}
    max_attempts: int = Field(default=5, ge=1, le=20)


class IncomingWebhookCreate(BaseModel):
    provider: str = Field(min_length=2, max_length=100)
    event_type: str = Field(min_length=2, max_length=255)
    payload: dict[str, Any] = {}


class WebhookEventResponse(BaseModel):
    id: int
    event_type: str
    source: str
    entity_type: str | None
    entity_id: str | None
    payload: dict[str, Any]
    status: WebhookEventStatus
    attempts_count: int
    max_attempts: int
    next_attempt_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WebhookDeliveryResponse(BaseModel):
    id: int
    webhook_event_id: int
    webhook_endpoint_id: int
    status: WebhookDeliveryStatus
    attempt_number: int
    request_headers: dict[str, Any] | None
    request_body: dict[str, Any] | None
    response_status_code: int | None
    response_body: str | None
    error_message: str | None
    duration_ms: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WebhookTestRequest(BaseModel):
    payload: dict[str, Any] = {
        "message": "This is a test webhook event."
    }


class WebhookEventRetryRequest(BaseModel):
    force: bool = False


class IncomingWebhookResponse(BaseModel):
    received: bool
    provider: str
    event_type: str
    message: str = "Incoming webhook received successfully."