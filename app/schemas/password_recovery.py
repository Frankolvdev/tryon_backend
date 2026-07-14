from datetime import datetime

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
)


class PasswordRecoveryRequest(BaseModel):
    email: EmailStr


class PasswordRecoveryRequestResponse(BaseModel):
    success: bool
    message: str

    verification_method: str

    challenge_id: int | None = None
    expires_at: datetime | None = None

    debug_otp: str | None = None
    debug_link_token: str | None = None


class PasswordRecoveryConfirmRequest(BaseModel):
    email: EmailStr

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

    new_password: str = Field(
        min_length=8,
        max_length=128,
    )


class PasswordRecoveryConfirmResponse(BaseModel):
    success: bool
    message: str

    revoked_sessions: int = 0
    password_changed_at: datetime | None = None


class RevokeSessionsResponse(BaseModel):
    success: bool
    revoked_sessions: int
    message: str