from datetime import datetime

from pydantic import (
    BaseModel,
    Field,
)


class AdminMfaStatusResponse(BaseModel):
    user_id: int

    required: bool
    configured: bool
    enabled: bool

    method: str | None = None
    verified_at: datetime | None = None
    last_used_at: datetime | None = None

    recovery_codes_remaining: int = 0


class AdminMfaSetupResponse(BaseModel):
    success: bool

    secret: str
    provisioning_uri: str

    recovery_codes: list[str]

    message: str


class AdminMfaVerifySetupRequest(BaseModel):
    code: str = Field(
        min_length=6,
        max_length=12,
    )


class AdminMfaCodeRequest(BaseModel):
    code: str = Field(
        min_length=6,
        max_length=100,
    )


class AdminMfaRecoveryCodesResponse(BaseModel):
    success: bool
    recovery_codes: list[str]
    message: str


class AdminMfaOperationResponse(BaseModel):
    success: bool
    message: str