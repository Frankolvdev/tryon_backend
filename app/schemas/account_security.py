from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)

from app.common.account_security_enums import (
    AccountVerificationMethod,
    AccountVerificationPurpose,
)


class AccountSecuritySettingsUpdate(BaseModel):
    registration_enabled: bool = True
    verification_required: bool = True

    verification_method: str = Field(
        default=(
            AccountVerificationMethod
            .OTP_AND_EMAIL_LINK
            .value
        ),
        max_length=40,
    )

    allow_login_before_verification: bool = False

    otp_length: int = Field(
        default=6,
        ge=4,
        le=10,
    )

    otp_expiration_minutes: int = Field(
        default=15,
        ge=1,
        le=1440,
    )

    otp_max_attempts: int = Field(
        default=5,
        ge=1,
        le=50,
    )

    otp_resend_cooldown_seconds: int = Field(
        default=60,
        ge=0,
        le=86400,
    )

    otp_max_resends_per_hour: int = Field(
        default=5,
        ge=1,
        le=100,
    )

    email_link_expiration_minutes: int = Field(
        default=60,
        ge=1,
        le=10080,
    )

    delete_unverified_accounts_after_days: int = Field(
        default=7,
        ge=1,
        le=365,
    )

    turnstile_enabled: bool = False
    block_disposable_email: bool = True

    require_terms_acceptance: bool = True
    require_age_confirmation: bool = True

    minimum_age: int = Field(
        default=18,
        ge=13,
        le=100,
    )

    max_accounts_per_ip_per_day: int = Field(
        default=3,
        ge=1,
        le=1000,
    )

    max_registrations_per_device_per_day: int = Field(
        default=2,
        ge=1,
        le=1000,
    )

    admin_mfa_required: bool = True

    @field_validator(
        "verification_method",
        mode="before",
    )
    @classmethod
    def normalize_verification_method(
        cls,
        value: str,
    ) -> str:
        normalized = str(value).strip().lower()

        valid_values = {
            item.value
            for item in AccountVerificationMethod
        }

        if normalized not in valid_values:
            raise ValueError(
                "Invalid verification method."
            )

        return normalized


class AccountSecuritySettingsResponse(BaseModel):
    id: int

    registration_enabled: bool
    verification_required: bool
    verification_method: str
    allow_login_before_verification: bool

    otp_length: int
    otp_expiration_minutes: int
    otp_max_attempts: int
    otp_resend_cooldown_seconds: int
    otp_max_resends_per_hour: int

    email_link_expiration_minutes: int
    delete_unverified_accounts_after_days: int

    turnstile_enabled: bool
    block_disposable_email: bool

    require_terms_acceptance: bool
    require_age_confirmation: bool
    minimum_age: int

    max_accounts_per_ip_per_day: int
    max_registrations_per_device_per_day: int

    admin_mfa_required: bool

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class AccountVerificationRequest(BaseModel):
    email: EmailStr

    purpose: str = Field(
        default=(
            AccountVerificationPurpose
            .REGISTRATION
            .value
        ),
        max_length=40,
    )

    @field_validator(
        "purpose",
        mode="before",
    )
    @classmethod
    def normalize_purpose(
        cls,
        value: str,
    ) -> str:
        normalized = str(value).strip().lower()

        valid_values = {
            item.value
            for item in AccountVerificationPurpose
        }

        if normalized not in valid_values:
            raise ValueError(
                "Invalid verification purpose."
            )

        return normalized


class AccountVerificationRequestResponse(BaseModel):
    success: bool
    message: str
    verification_method: str

    challenge_id: int | None = None
    expires_at: datetime | None = None

    debug_otp: str | None = None
    debug_link_token: str | None = None


class AccountVerificationConfirmRequest(BaseModel):
    email: EmailStr

    purpose: str = Field(
        default=(
            AccountVerificationPurpose
            .REGISTRATION
            .value
        ),
        max_length=40,
    )

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

    @field_validator(
        "purpose",
        mode="before",
    )
    @classmethod
    def normalize_purpose(
        cls,
        value: str,
    ) -> str:
        normalized = str(value).strip().lower()

        valid_values = {
            item.value
            for item in AccountVerificationPurpose
        }

        if normalized not in valid_values:
            raise ValueError(
                "Invalid verification purpose."
            )

        return normalized


class AccountVerificationConfirmResponse(BaseModel):
    success: bool
    verified: bool
    message: str

    user_id: int | None = None
    account_status: str | None = None
    email_verified_at: datetime | None = None


class AccountVerificationStatusResponse(BaseModel):
    user_id: int

    account_status: str
    verification_required: bool

    email_verified: bool
    email_verified_at: datetime | None

    terms_accepted: bool
    age_confirmed: bool

    locked_until: datetime | None


class AdminVerifyUserRequest(BaseModel):
    reason: str = Field(
        min_length=3,
        max_length=1000,
    )


class AdminResendVerificationRequest(BaseModel):
    reason: str | None = Field(
        default=None,
        max_length=1000,
    )


class AdminCancelVerificationRequest(BaseModel):
    reason: str = Field(
        min_length=3,
        max_length=1000,
    )


class AdminAccountVerificationResponse(BaseModel):
    success: bool
    user_id: int
    email: str

    account_status: str
    email_verified: bool
    email_verified_at: datetime | None

    message: str


class AccountVerificationChallengeResponse(BaseModel):
    id: int
    user_id: int | None
    email: str

    purpose: str
    verification_method: str
    status: str

    attempt_count: int
    max_attempts: int
    resend_count: int

    requested_ip: str | None

    expires_at: datetime
    last_sent_at: datetime
    verified_at: datetime | None
    consumed_at: datetime | None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class AccountVerificationChallengeListResponse(BaseModel):
    items: list[
        AccountVerificationChallengeResponse
    ]

    total: int
    skip: int
    limit: int


class UnverifiedAccountResponse(BaseModel):
    user_id: int
    email: str

    account_status: str
    email_verified: bool

    created_at: datetime
    eligible_for_cleanup_at: datetime
    is_eligible_for_cleanup: bool


class UnverifiedAccountListResponse(BaseModel):
    items: list[UnverifiedAccountResponse]

    total: int
    cleanup_after_days: int

    skip: int
    limit: int


class UnverifiedCleanupRequest(BaseModel):
    dry_run: bool = True

    limit: int = Field(
        default=500,
        ge=1,
        le=10000,
    )


class UnverifiedCleanupResponse(BaseModel):
    success: bool
    dry_run: bool

    cutoff_at: datetime
    scanned: int
    eligible: int
    deactivated: int

    challenges_cancelled: int
    sessions_revoked: int

    user_ids: list[int]

    message: str