from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
)


class EmailChangeCreate(BaseModel):
    new_email: EmailStr

    current_password: str = Field(
        min_length=1,
        max_length=128,
    )


class EmailChangeRequestResponse(BaseModel):
    success: bool
    message: str

    request_id: int | None = None
    verification_method: str

    expires_at: datetime | None = None

    debug_otp: str | None = None
    debug_link_token: str | None = None


class EmailChangeConfirmRequest(BaseModel):
    new_email: EmailStr

    otp: str | None = Field(
        default=None,
        min_length=4,
        max_length=20,
    )

    token: str | None = Field(
        default=None,
        min_length=20,
        max_length=1000,
    )


class EmailChangeConfirmResponse(BaseModel):
    success: bool
    message: str

    user_id: int
    old_email: str
    new_email: str

    revoked_sessions: int
    changed_at: datetime


class EmailChangeCancelResponse(BaseModel):
    success: bool
    cancelled_requests: int
    message: str


class EmailChangeRequestItem(BaseModel):
    id: int
    user_id: int

    current_email: str
    new_email: str

    verification_method: str
    status: str

    attempt_count: int
    max_attempts: int
    resend_count: int

    requested_ip: str | None

    expires_at: datetime
    last_sent_at: datetime

    verified_at: datetime | None
    cancelled_at: datetime | None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class EmailChangeRequestListResponse(BaseModel):
    items: list[EmailChangeRequestItem]

    total: int
    skip: int
    limit: int