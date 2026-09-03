from datetime import datetime, time
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class AdminNotificationPreferenceUpdate(BaseModel):
    is_enabled: bool = True

    minimum_priority: str = Field(
        default="normal",
        max_length=30,
    )

    digest_mode: str = Field(
        default="immediate",
        max_length=30,
    )

    enabled_sources: list[str] = Field(
        default_factory=list,
        max_length=100,
    )

    enabled_types: list[str] = Field(
        default_factory=list,
        max_length=20,
    )

    quiet_hours_enabled: bool = False

    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None

    timezone: str = Field(
        default="America/Mexico_City",
        min_length=1,
        max_length=100,
    )

    allow_urgent_during_quiet_hours: bool = True
    allow_critical_during_quiet_hours: bool = True

    @field_validator(
        "minimum_priority",
        "digest_mode",
        mode="before",
    )
    @classmethod
    def normalize_values(
        cls,
        value: str,
    ) -> str:
        return str(value).strip().lower()


class AdminNotificationPreferenceResponse(BaseModel):
    id: int
    user_id: int

    is_enabled: bool

    minimum_priority: str
    digest_mode: str

    enabled_sources: list[str]
    enabled_types: list[str]

    quiet_hours_enabled: bool
    quiet_hours_start: time | None
    quiet_hours_end: time | None

    timezone: str

    allow_urgent_during_quiet_hours: bool
    allow_critical_during_quiet_hours: bool

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class AdminNotificationChannelCreate(BaseModel):
    channel_type: str = Field(
        min_length=2,
        max_length=30,
    )

    is_enabled: bool = True

    destination: str | None = Field(
        default=None,
        max_length=2000,
    )

    display_name: str | None = Field(
        default=None,
        max_length=150,
    )

    integration_provider: str | None = Field(
        default=None,
        max_length=100,
    )

    configuration: dict[str, Any] = Field(
        default_factory=dict,
    )

    minimum_priority: str = Field(
        default="normal",
        max_length=30,
    )

    send_success_notifications: bool = False
    send_info_notifications: bool = True
    send_warning_notifications: bool = True
    send_error_notifications: bool = True
    send_critical_notifications: bool = True

    @field_validator(
        "channel_type",
        "minimum_priority",
        mode="before",
    )
    @classmethod
    def normalize_values(
        cls,
        value: str,
    ) -> str:
        return str(value).strip().lower()


class AdminNotificationChannelUpdate(BaseModel):
    is_enabled: bool | None = None

    destination: str | None = Field(
        default=None,
        max_length=2000,
    )

    display_name: str | None = Field(
        default=None,
        max_length=150,
    )

    integration_provider: str | None = Field(
        default=None,
        max_length=100,
    )

    configuration: dict[str, Any] | None = None

    minimum_priority: str | None = Field(
        default=None,
        max_length=30,
    )

    send_success_notifications: bool | None = None
    send_info_notifications: bool | None = None
    send_warning_notifications: bool | None = None
    send_error_notifications: bool | None = None
    send_critical_notifications: bool | None = None

    @field_validator(
        "minimum_priority",
        mode="before",
    )
    @classmethod
    def normalize_priority(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        return str(value).strip().lower()


class AdminNotificationChannelResponse(BaseModel):
    id: int
    user_id: int

    channel_type: str

    is_enabled: bool
    status: str

    destination: str | None
    display_name: str | None
    integration_provider: str | None

    configuration: dict[str, Any]

    minimum_priority: str

    send_success_notifications: bool
    send_info_notifications: bool
    send_warning_notifications: bool
    send_error_notifications: bool
    send_critical_notifications: bool

    last_tested_at: datetime | None
    last_test_success: bool | None
    last_error: str | None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class AdminNotificationSettingsResponse(BaseModel):
    preference: AdminNotificationPreferenceResponse

    channels: list[
        AdminNotificationChannelResponse
    ]


class NotificationRoutingPreviewRequest(BaseModel):
    notification_type: str
    priority: str
    source: str

    created_at: datetime | None = None


class NotificationRoutingPreviewChannel(BaseModel):
    channel_type: str
    selected: bool
    reason: str


class NotificationRoutingPreviewResponse(BaseModel):
    will_notify: bool
    is_quiet_hours: bool

    selected_channels: list[str]

    channels: list[
        NotificationRoutingPreviewChannel
    ]