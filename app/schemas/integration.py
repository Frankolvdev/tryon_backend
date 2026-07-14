from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import (
    IntegrationHealthStatus,
    IntegrationProvider,
    IntegrationStatus,
)


class IntegrationConfigCreate(BaseModel):
    provider: IntegrationProvider
    name: str = Field(min_length=2, max_length=255)
    status: IntegrationStatus = IntegrationStatus.DISABLED
    is_enabled: bool = False

    base_url: str | None = None
    api_key: str | None = None
    api_secret: str | None = None
    webhook_secret: str | None = None

    config: dict[str, Any] = {}


class IntegrationConfigUpdate(BaseModel):
    name: str | None = None
    status: IntegrationStatus | None = None
    is_enabled: bool | None = None

    base_url: str | None = None
    api_key: str | None = None
    api_secret: str | None = None
    webhook_secret: str | None = None

    config: dict[str, Any] | None = None


class IntegrationConfigResponse(BaseModel):
    id: int
    provider: IntegrationProvider
    name: str
    status: IntegrationStatus
    is_enabled: bool
    base_url: str | None
    api_key_configured: bool
    api_secret_configured: bool
    webhook_secret_configured: bool
    config: dict[str, Any]
    last_health_status: str | None
    last_health_message: str | None
    last_checked_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IntegrationHealthResponse(BaseModel):
    provider: IntegrationProvider
    status: IntegrationHealthStatus
    message: str
    metadata: dict[str, Any] = {}


class IntegrationEventResponse(BaseModel):
    id: int
    provider: IntegrationProvider
    event_type: str
    entity_type: str | None
    entity_id: str | None
    payload: dict[str, Any] | None
    response: dict[str, Any] | None
    error_message: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IntegrationSeedResponse(BaseModel):
    created: int
    skipped: int
    total: int