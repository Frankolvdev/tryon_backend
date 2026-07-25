from pydantic import (
    BaseModel,
    EmailStr,
    Field,
)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    mfa_code: str | None = Field(
        default=None,
        min_length=6,
        max_length=100,
    )


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str

    token_type: str = "bearer"

    mfa_setup_required: bool = False