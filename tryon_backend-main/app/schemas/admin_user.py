from pydantic import BaseModel, EmailStr, Field

from app.common.enums import UserRole, UserStatus


class AdminUserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None
    role: UserRole = UserRole.USER
    status: UserStatus = UserStatus.ACTIVE
    is_active: bool = True
    is_verified: bool = False
    token_balance: int = Field(default=0, ge=0)


class AdminUserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = None
    role: UserRole | None = None
    status: UserStatus | None = None
    is_active: bool | None = None
    is_verified: bool | None = None
    token_balance: int | None = Field(default=None, ge=0)


class AdminUserPasswordReset(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


class AdminUserTokenAdjustment(BaseModel):
    amount: int
    reason: str | None = None