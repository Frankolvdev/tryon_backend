from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.common.rate_limit_enums import RateLimitAction


class RateLimitIdentity(BaseModel):
    ip_address: str | None = None
    user_id: int | None = None
    api_key_id: int | None = None
    api_key_hash: str | None = None
    is_authenticated: bool = False


class RateLimitCheckResult(BaseModel):
    allowed: bool
    action: RateLimitAction

    policy_id: int | None = None
    policy_key: str | None = None

    identifier: str
    request_count: int
    request_limit: int
    remaining: int

    window_seconds: int
    reset_at: datetime
    retry_after_seconds: int

    blocked: bool
    blocked_until: datetime | None = None

    redis_available: bool = True
    fallback_used: bool = False

    metadata: dict[str, Any] = {}