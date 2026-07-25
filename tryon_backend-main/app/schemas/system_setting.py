from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import SettingCategory, SettingValueType


class SystemSettingCreate(BaseModel):
    category: SettingCategory = SettingCategory.SYSTEM
    key: str = Field(min_length=2, max_length=255)
    label: str = Field(min_length=2, max_length=255)
    description: str | None = None
    value_type: SettingValueType = SettingValueType.STRING

    value: Any | None = None
    default_value: Any | None = None

    is_public: bool = False
    is_editable: bool = True
    is_sensitive: bool = False
    requires_restart: bool = False
    sort_order: int = 0


class SystemSettingUpdate(BaseModel):
    label: str | None = None
    description: str | None = None
    value: Any | None = None
    default_value: Any | None = None

    is_public: bool | None = None
    is_editable: bool | None = None
    is_sensitive: bool | None = None
    requires_restart: bool | None = None
    sort_order: int | None = None


class SystemSettingResponse(BaseModel):
    id: int
    category: SettingCategory
    key: str
    label: str
    description: str | None
    value_type: SettingValueType
    value: Any | None
    default_value: Any | None
    is_public: bool
    is_editable: bool
    is_sensitive: bool
    requires_restart: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PublicSystemSettingResponse(BaseModel):
    key: str
    value: Any | None


class SystemSettingsByCategoryResponse(BaseModel):
    category: SettingCategory
    settings: list[SystemSettingResponse]


class SystemSettingsGroupedResponse(BaseModel):
    categories: dict[str, list[SystemSettingResponse]]


class PublicFrontendConfigResponse(BaseModel):
    app_name: str | None = None
    support_email: str | None = None
    frontend_base_url: str | None = None
    registration_enabled: bool = True
    email_login_enabled: bool = True
    social_login_enabled: bool = False
    billing_enabled: bool = False
    subscriptions_enabled: bool = False
    tryon_enabled: bool = True
    footwear_tryon_enabled: bool = True
    high_quality_enabled: bool = True
    maintenance_mode: bool = False
    max_upload_size_mb: int = 25
    public_settings: dict[str, Any] = {}