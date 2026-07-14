from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import ApiKeyStatus, ApiKeyType


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    api_key_type: ApiKeyType = ApiKeyType.INTEGRATION
    user_id: int | None = None
    scopes: list[str] = []
    allowed_ips: list[str] = []
    description: str | None = None
    expires_at: datetime | None = None


class ApiKeyUpdate(BaseModel):
    name: str | None = None
    scopes: list[str] | None = None
    allowed_ips: list[str] | None = None
    description: str | None = None
    expires_at: datetime | None = None
    is_active: bool | None = None


class ApiKeyResponse(BaseModel):
    id: int
    name: str
    key_prefix: str
    api_key_type: ApiKeyType
    status: ApiKeyStatus
    user_id: int | None
    created_by_user_id: int | None
    scopes: list[str]
    allowed_ips: list[str]
    description: str | None
    is_active: bool
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApiKeyCreateResponse(BaseModel):
    api_key: str
    warning: str = "Copy this API key now. It will not be shown again."
    record: ApiKeyResponse


class ApiKeyValidationResponse(BaseModel):
    valid: bool
    api_key_id: int | None = None
    user_id: int | None = None
    scopes: list[str] = []
    metadata: dict[str, Any] = {}


class ApiKeyRevokeResponse(BaseModel):
    message: str = "API key revoked successfully."