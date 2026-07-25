from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


def normalize_locale_code_value(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    raw = str(value).strip().replace("_", "-")

    if not raw:
        return None

    parts = raw.split("-")

    if len(parts) == 1:
        return parts[0].lower()

    return (
        parts[0].lower()
        + "-"
        + parts[1].upper()
    )


class I18nLocaleCreate(BaseModel):
    code: str = Field(
        min_length=2,
        max_length=20,
    )

    name: str = Field(
        min_length=1,
        max_length=150,
    )

    native_name: str = Field(
        min_length=1,
        max_length=150,
    )

    fallback_locale_code: str | None = Field(
        default=None,
        max_length=20,
    )

    currency_code: str = Field(
        default="USD",
        min_length=3,
        max_length=10,
    )

    timezone: str = Field(
        default="UTC",
        min_length=1,
        max_length=100,
    )

    date_format: str = Field(
        default="YYYY-MM-DD",
        min_length=1,
        max_length=50,
    )

    time_format: str = Field(
        default="HH:mm",
        min_length=1,
        max_length=50,
    )

    is_active: bool = True
    is_default: bool = False

    @field_validator(
        "code",
        "fallback_locale_code",
        mode="before",
    )
    @classmethod
    def normalize_locale_code(
        cls,
        value: str | None,
    ) -> str | None:
        return normalize_locale_code_value(
            value
        )

    @field_validator(
        "currency_code",
        mode="before",
    )
    @classmethod
    def normalize_currency(
        cls,
        value: str,
    ) -> str:
        return str(value).strip().upper()


class I18nLocaleUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
    )

    native_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
    )

    fallback_locale_code: str | None = Field(
        default=None,
        max_length=20,
    )

    currency_code: str | None = Field(
        default=None,
        min_length=3,
        max_length=10,
    )

    timezone: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    date_format: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )

    time_format: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )

    is_active: bool | None = None
    is_default: bool | None = None

    @field_validator(
        "fallback_locale_code",
        mode="before",
    )
    @classmethod
    def normalize_fallback_locale(
        cls,
        value: str | None,
    ) -> str | None:
        return normalize_locale_code_value(
            value
        )

    @field_validator(
        "currency_code",
        mode="before",
    )
    @classmethod
    def normalize_currency(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        return str(value).strip().upper()


class I18nLocaleResponse(BaseModel):
    code: str
    name: str
    native_name: str

    fallback_locale_code: str | None

    currency_code: str
    timezone: str
    date_format: str
    time_format: str

    is_active: bool
    is_default: bool

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class I18nLocaleListResponse(BaseModel):
    items: list[I18nLocaleResponse]
    total: int


class I18nTranslationCreate(BaseModel):
    locale_code: str = Field(
        min_length=2,
        max_length=20,
    )

    translation_key: str = Field(
        min_length=1,
        max_length=255,
    )

    value: str = Field(
        min_length=1,
        max_length=50000,
    )

    description: str | None = Field(
        default=None,
        max_length=10000,
    )

    is_html: bool = False
    is_active: bool = True

    @field_validator(
        "locale_code",
        mode="before",
    )
    @classmethod
    def normalize_locale(
        cls,
        value: str,
    ) -> str:
        normalized = normalize_locale_code_value(
            value
        )

        return normalized or str(value)

    @field_validator(
        "translation_key",
        mode="before",
    )
    @classmethod
    def normalize_key(
        cls,
        value: str,
    ) -> str:
        return str(value).strip()


class I18nTranslationUpdate(BaseModel):
    value: str | None = Field(
        default=None,
        min_length=1,
        max_length=50000,
    )

    description: str | None = Field(
        default=None,
        max_length=10000,
    )

    is_html: bool | None = None
    is_active: bool | None = None


class I18nTranslationResponse(BaseModel):
    id: int

    locale_code: str
    namespace: str
    translation_key: str

    value: str
    description: str | None

    is_html: bool
    is_active: bool

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class I18nTranslationListResponse(BaseModel):
    items: list[I18nTranslationResponse]

    total: int
    skip: int
    limit: int


class UserLocalePreferenceUpdate(BaseModel):
    locale_code: str = Field(
        min_length=2,
        max_length=20,
    )

    timezone: str | None = Field(
        default=None,
        max_length=100,
    )

    currency_code: str | None = Field(
        default=None,
        max_length=10,
    )

    date_format: str | None = Field(
        default=None,
        max_length=50,
    )

    time_format: str | None = Field(
        default=None,
        max_length=50,
    )

    @field_validator(
        "locale_code",
        mode="before",
    )
    @classmethod
    def normalize_locale(
        cls,
        value: str,
    ) -> str:
        normalized = normalize_locale_code_value(
            value
        )

        return normalized or str(value)

    @field_validator(
        "currency_code",
        mode="before",
    )
    @classmethod
    def normalize_currency(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        return str(value).strip().upper()


class UserLocalePreferenceResponse(BaseModel):
    id: int
    user_id: int

    locale_code: str
    timezone: str | None
    currency_code: str | None
    date_format: str | None
    time_format: str | None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class ResolvedLocaleResponse(BaseModel):
    locale_code: str
    fallback_locale_code: str | None

    timezone: str
    currency_code: str
    date_format: str
    time_format: str


class TranslationDictionaryResponse(BaseModel):
    locale_code: str
    translations: dict[str, str]


class I18nSeedResponse(BaseModel):
    success: bool
    locales_processed: int
    translations_processed: int
    message: str