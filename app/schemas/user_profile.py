from datetime import datetime
from re import fullmatch

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


PROFILE_VISIBILITY_VALUES = {
    "private",
    "registered_users",
    "public",
}

GALLERY_VISIBILITY_VALUES = {
    "private",
    "registered_users",
    "public",
}


class UserProfileUpdate(BaseModel):
    full_name: str | None = Field(
        default=None,
        max_length=255,
    )

    username: str | None = Field(
        default=None,
        min_length=3,
        max_length=50,
    )

    biography: str | None = Field(
        default=None,
        max_length=2000,
    )

    country_code: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
    )

    timezone: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    locale_code: str | None = Field(
        default=None,
        min_length=2,
        max_length=20,
    )

    currency_code: str | None = Field(
        default=None,
        min_length=3,
        max_length=10,
    )

    profile_visibility: str | None = Field(
        default=None,
        max_length=30,
    )

    gallery_visibility: str | None = Field(
        default=None,
        max_length=30,
    )

    show_activity_status: bool | None = None
    allow_marketing_emails: bool | None = None
    allow_product_updates: bool | None = None

    retain_input_images: bool | None = None
    retain_generated_images: bool | None = None

    @field_validator(
        "username",
        mode="before",
    )
    @classmethod
    def normalize_username(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = str(value).strip().lower()

        if not normalized:
            return None

        if not fullmatch(
            r"[a-z0-9][a-z0-9._-]{1,48}[a-z0-9]",
            normalized,
        ):
            raise ValueError(
                "Username may only contain lowercase letters, "
                "numbers, dots, underscores and hyphens."
            )

        return normalized

    @field_validator(
        "country_code",
        mode="before",
    )
    @classmethod
    def normalize_country_code(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = str(value).strip().upper()

        return normalized or None

    @field_validator(
        "currency_code",
        mode="before",
    )
    @classmethod
    def normalize_currency_code(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        return str(value).strip().upper()

    @field_validator(
        "locale_code",
        mode="before",
    )
    @classmethod
    def normalize_locale_code(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        raw_value = str(value).strip().replace("_", "-")

        if not raw_value:
            return None

        parts = raw_value.split("-")

        if len(parts) == 1:
            return parts[0].lower()

        return (
            parts[0].lower()
            + "-"
            + parts[1].upper()
        )

    @field_validator(
        "profile_visibility",
        mode="before",
    )
    @classmethod
    def validate_profile_visibility(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = str(value).strip().lower()

        if normalized not in PROFILE_VISIBILITY_VALUES:
            raise ValueError(
                "Invalid profile visibility."
            )

        return normalized

    @field_validator(
        "gallery_visibility",
        mode="before",
    )
    @classmethod
    def validate_gallery_visibility(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = str(value).strip().lower()

        if normalized not in GALLERY_VISIBILITY_VALUES:
            raise ValueError(
                "Invalid gallery visibility."
            )

        return normalized


class UserPrivacyUpdate(BaseModel):
    profile_visibility: str | None = None
    gallery_visibility: str | None = None

    show_activity_status: bool | None = None

    allow_marketing_emails: bool | None = None
    allow_product_updates: bool | None = None

    retain_input_images: bool | None = None
    retain_generated_images: bool | None = None

    @field_validator(
        "profile_visibility",
        mode="before",
    )
    @classmethod
    def validate_profile_visibility(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = str(value).strip().lower()

        if normalized not in PROFILE_VISIBILITY_VALUES:
            raise ValueError(
                "Invalid profile visibility."
            )

        return normalized

    @field_validator(
        "gallery_visibility",
        mode="before",
    )
    @classmethod
    def validate_gallery_visibility(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = str(value).strip().lower()

        if normalized not in GALLERY_VISIBILITY_VALUES:
            raise ValueError(
                "Invalid gallery visibility."
            )

        return normalized


class ImageProcessingConsentUpdate(BaseModel):
    accepted: bool


class OnboardingCompleteRequest(BaseModel):
    image_processing_consent: bool = True


class UserProfileResponse(BaseModel):
    user_id: int

    email: str
    full_name: str | None

    username: str | None
    biography: str | None

    avatar_file_id: int | None

    country_code: str | None
    timezone: str
    locale_code: str
    currency_code: str

    profile_visibility: str
    gallery_visibility: str

    show_activity_status: bool

    allow_marketing_emails: bool
    allow_product_updates: bool
    allow_security_emails: bool

    image_processing_consent: bool
    image_processing_consent_at: datetime | None

    retain_input_images: bool
    retain_generated_images: bool

    profile_completed: bool
    onboarding_completed: bool
    onboarding_completed_at: datetime | None

    is_verified: bool
    is_active: bool

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class UserPrivacyResponse(BaseModel):
    profile_visibility: str
    gallery_visibility: str

    show_activity_status: bool

    allow_marketing_emails: bool
    allow_product_updates: bool
    allow_security_emails: bool

    image_processing_consent: bool
    image_processing_consent_at: datetime | None

    retain_input_images: bool
    retain_generated_images: bool


class UserOnboardingStatusResponse(BaseModel):
    profile_completed: bool
    onboarding_completed: bool

    email_verified: bool
    image_processing_consent: bool

    missing_steps: list[str]