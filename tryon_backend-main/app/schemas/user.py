from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
)

from app.common.enums import (
    UserRole,
    UserStatus,
)


class UserBase(BaseModel):
    email: EmailStr

    full_name: str | None = Field(
        default=None,
        max_length=255,
    )


class UserCreate(UserBase):
    password: str = Field(
        min_length=8,
        max_length=128,
    )

    terms_accepted: bool = False

    terms_version: str | None = Field(
        default=None,
        max_length=100,
    )

    age_confirmed: bool = False

    turnstile_token: str | None = Field(
        default=None,
        max_length=4096,
    )


class UserUpdate(BaseModel):
    full_name: str | None = Field(
        default=None,
        max_length=255,
    )


class UserPasswordChange(BaseModel):
    current_password: str

    new_password: str = Field(
        min_length=8,
        max_length=128,
    )


class UserResponse(UserBase):
    id: int
    avatar_file_id: int | None
    auth_provider: str

    role: UserRole
    status: UserStatus

    is_active: bool
    is_verified: bool
    token_balance: int

    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    model_config = ConfigDict(
        from_attributes=True,
    )