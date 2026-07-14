from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


class SessionResponse(BaseModel):
    id: int

    user_agent: str | None
    ip_address: str | None

    is_revoked: bool

    expires_at: datetime
    created_at: datetime
    revoked_at: datetime | None

    is_expired: bool = False
    is_current: bool = False

    device_name: str | None = None
    browser_name: str | None = None
    operating_system: str | None = None

    model_config = ConfigDict(
        from_attributes=True,
    )


class SessionListResponse(BaseModel):
    items: list[SessionResponse]
    total: int
    active: int
    revoked: int
    expired: int


class SessionRevokeResponse(BaseModel):
    success: bool
    session_id: int
    message: str


class SessionsRevokeResponse(BaseModel):
    success: bool
    revoked_sessions: int
    message: str


class RevokeOtherSessionsRequest(BaseModel):
    current_session_id: int = Field(
        ge=1,
    )