from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.common.rate_limit_enums import (
    AbuseEventStatus,
    AbuseEventType,
    AbuseSeverity,
    BlockTargetType,
    RateLimitAlgorithm,
    RateLimitScope,
)


class RateLimitPolicyCreate(BaseModel):
    key: str = Field(
        min_length=2,
        max_length=150,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    )

    name: str = Field(min_length=2, max_length=255)
    description: str | None = None

    route_pattern: str = Field(
        min_length=1,
        max_length=500,
    )

    http_method: str | None = Field(
        default=None,
        max_length=20,
    )

    scope: RateLimitScope = RateLimitScope.IP
    algorithm: RateLimitAlgorithm = (
        RateLimitAlgorithm.SLIDING_WINDOW
    )

    request_limit: int = Field(ge=1)
    window_seconds: int = Field(ge=1)
    burst_limit: int | None = Field(default=None, ge=1)
    block_seconds: int = Field(default=0, ge=0)

    priority: int = Field(default=100, ge=0, le=10000)

    applies_to_authenticated: bool = True
    applies_to_anonymous: bool = True
    include_headers: bool = True
    is_enabled: bool = True

    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("http_method")
    @classmethod
    def normalize_method(
        cls,
        value: str | None,
    ) -> str | None:
        return value.upper() if value else None


class RateLimitPolicyUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=255,
    )

    description: str | None = None
    route_pattern: str | None = Field(
        default=None,
        min_length=1,
        max_length=500,
    )

    http_method: str | None = Field(
        default=None,
        max_length=20,
    )

    scope: RateLimitScope | None = None
    algorithm: RateLimitAlgorithm | None = None

    request_limit: int | None = Field(default=None, ge=1)
    window_seconds: int | None = Field(default=None, ge=1)
    burst_limit: int | None = Field(default=None, ge=1)
    block_seconds: int | None = Field(default=None, ge=0)

    priority: int | None = Field(
        default=None,
        ge=0,
        le=10000,
    )

    applies_to_authenticated: bool | None = None
    applies_to_anonymous: bool | None = None
    include_headers: bool | None = None
    is_enabled: bool | None = None

    metadata: dict[str, Any] | None = None

    @field_validator("http_method")
    @classmethod
    def normalize_method(
        cls,
        value: str | None,
    ) -> str | None:
        return value.upper() if value else None


class RateLimitPolicyResponse(BaseModel):
    id: int
    key: str
    name: str
    description: str | None

    route_pattern: str
    http_method: str | None

    scope: RateLimitScope
    algorithm: RateLimitAlgorithm

    request_limit: int
    window_seconds: int
    burst_limit: int | None
    block_seconds: int

    priority: int

    applies_to_authenticated: bool
    applies_to_anonymous: bool
    include_headers: bool
    is_enabled: bool

    metadata: dict[str, Any]

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RateLimitPolicyListResponse(BaseModel):
    items: list[RateLimitPolicyResponse]
    total: int
    skip: int
    limit: int


class AbuseEventResponse(BaseModel):
    id: int

    event_type: AbuseEventType
    severity: AbuseSeverity
    status: AbuseEventStatus

    rate_limit_policy_id: int | None
    user_id: int | None
    api_key_id: int | None

    ip_address: str | None
    user_agent: str | None

    route: str | None
    http_method: str | None
    identifier: str | None

    request_count: int | None
    request_limit: int | None
    window_seconds: int | None

    blocked_until: datetime | None

    details: dict[str, Any]

    reviewed_by_user_id: int | None
    reviewed_at: datetime | None
    resolution_notes: str | None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AbuseEventListResponse(BaseModel):
    items: list[AbuseEventResponse]
    total: int
    skip: int
    limit: int


class AbuseEventReviewRequest(BaseModel):
    status: AbuseEventStatus
    resolution_notes: str | None = None


class SecurityBlockCreate(BaseModel):
    target_type: BlockTargetType
    target_value: str = Field(
        min_length=1,
        max_length=500,
    )

    reason: str = Field(min_length=2)
    abuse_event_id: int | None = None

    expires_at: datetime | None = None
    is_permanent: bool = False

    metadata: dict[str, Any] = Field(default_factory=dict)


class SecurityBlockResponse(BaseModel):
    id: int

    target_type: BlockTargetType
    target_value: str
    reason: str

    abuse_event_id: int | None
    created_by_user_id: int | None

    starts_at: datetime
    expires_at: datetime | None

    is_permanent: bool
    is_active: bool

    metadata: dict[str, Any]

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SecurityBlockListResponse(BaseModel):
    items: list[SecurityBlockResponse]
    total: int
    skip: int
    limit: int