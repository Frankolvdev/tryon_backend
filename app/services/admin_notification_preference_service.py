import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.common.exceptions import (
    ConflictException,
    NotFoundException,
)
from app.common.notification_delivery_enums import (
    NotificationChannelStatus,
    NotificationChannelType,
    NotificationDigestMode,
    NotificationMinimumPriority,
)
from app.common.notification_enums import (
    AdminNotificationPriority,
    AdminNotificationSource,
    AdminNotificationType,
)
from app.models.admin_notification_channel import (
    AdminNotificationChannel,
)
from app.models.admin_notification_preference import (
    AdminNotificationPreference,
)
from app.repositories.admin_notification_preference_repository import (
    admin_notification_preference_repository,
)
from app.schemas.admin_notification_preference import (
    AdminNotificationChannelCreate,
    AdminNotificationChannelResponse,
    AdminNotificationChannelUpdate,
    AdminNotificationPreferenceResponse,
    AdminNotificationPreferenceUpdate,
    AdminNotificationSettingsResponse,
    NotificationRoutingPreviewChannel,
    NotificationRoutingPreviewRequest,
    NotificationRoutingPreviewResponse,
)


class AdminNotificationPreferenceService:
    PRIORITY_RANK = {
        "low": 1,
        "normal": 2,
        "high": 3,
        "urgent": 4,
    }

    VALID_CHANNELS = {
        item.value
        for item in NotificationChannelType
    }

    VALID_DIGEST_MODES = {
        item.value
        for item in NotificationDigestMode
    }

    VALID_PRIORITIES = {
        item.value
        for item in NotificationMinimumPriority
    }

    VALID_TYPES = {
        item.value
        for item in AdminNotificationType
    }

    VALID_SOURCES = {
        item.value
        for item in AdminNotificationSource
    }

    DEFAULT_SOURCES = sorted(
        VALID_SOURCES
    )

    DEFAULT_TYPES = sorted(
        VALID_TYPES
    )

    def _dump_json(
        self,
        value: Any,
    ) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        )

    def _load_list(
        self,
        value: str | None,
        *,
        default: list[str],
    ) -> list[str]:
        if not value:
            return list(default)

        try:
            parsed = json.loads(value)

            if isinstance(parsed, list):
                return [
                    str(item)
                    for item in parsed
                ]

        except (
            TypeError,
            json.JSONDecodeError,
        ):
            pass

        return list(default)

    def _load_dict(
        self,
        value: str | None,
    ) -> dict[str, Any]:
        if not value:
            return {}

        try:
            parsed = json.loads(value)

            if isinstance(parsed, dict):
                return parsed

        except (
            TypeError,
            json.JSONDecodeError,
        ):
            pass

        return {}

    def _validate_timezone(
        self,
        timezone_name: str,
    ) -> str:
        try:
            ZoneInfo(timezone_name)

        except ZoneInfoNotFoundError as error:
            raise ConflictException(
                "Invalid IANA timezone."
            ) from error

        return timezone_name

    def _validate_priority(
        self,
        priority: str,
    ) -> str:
        normalized = priority.strip().lower()

        if normalized not in self.VALID_PRIORITIES:
            raise ConflictException(
                "Invalid notification priority."
            )

        return normalized

    def _validate_digest_mode(
        self,
        digest_mode: str,
    ) -> str:
        normalized = digest_mode.strip().lower()

        if normalized not in self.VALID_DIGEST_MODES:
            raise ConflictException(
                "Invalid notification digest mode."
            )

        return normalized

    def _validate_sources(
        self,
        sources: list[str],
    ) -> list[str]:
        normalized = sorted(
            {
                str(source).strip().lower()
                for source in sources
                if str(source).strip()
            }
        )

        invalid = [
            source
            for source in normalized
            if source not in self.VALID_SOURCES
        ]

        if invalid:
            raise ConflictException(
                "Invalid notification sources: "
                + ", ".join(invalid)
            )

        return normalized or list(
            self.DEFAULT_SOURCES
        )

    def _validate_types(
        self,
        notification_types: list[str],
    ) -> list[str]:
        normalized = sorted(
            {
                str(item).strip().lower()
                for item in notification_types
                if str(item).strip()
            }
        )

        invalid = [
            item
            for item in normalized
            if item not in self.VALID_TYPES
        ]

        if invalid:
            raise ConflictException(
                "Invalid notification types: "
                + ", ".join(invalid)
            )

        return normalized or list(
            self.DEFAULT_TYPES
        )

    def _validate_channel_destination(
        self,
        *,
        channel_type: str,
        destination: str | None,
    ) -> None:
        if channel_type == "backoffice":
            return

        if not destination:
            raise ConflictException(
                "This notification channel requires a destination."
            )

        if channel_type == "email":
            if (
                "@" not in destination
                or "." not in destination.split("@")[-1]
            ):
                raise ConflictException(
                    "Invalid email destination."
                )

            return

        if channel_type == "telegram":
            if not destination.strip():
                raise ConflictException(
                    "Telegram chat ID is required."
                )

            return

        if channel_type == "slack":
            if not destination.strip():
                raise ConflictException(
                    "Slack destination is required."
                )

            return

        if channel_type == "webhook":
            parsed = urlparse(destination)

            if (
                parsed.scheme != "https"
                or not parsed.netloc
            ):
                raise ConflictException(
                    "Webhook destination must be a valid HTTPS URL."
                )

    def _preference_response(
        self,
        preference: AdminNotificationPreference,
    ) -> AdminNotificationPreferenceResponse:
        return AdminNotificationPreferenceResponse(
            id=preference.id,
            user_id=preference.user_id,
            is_enabled=preference.is_enabled,
            minimum_priority=(
                preference.minimum_priority
            ),
            digest_mode=preference.digest_mode,
            enabled_sources=self._load_list(
                preference.enabled_sources_json,
                default=self.DEFAULT_SOURCES,
            ),
            enabled_types=self._load_list(
                preference.enabled_types_json,
                default=self.DEFAULT_TYPES,
            ),
            quiet_hours_enabled=(
                preference.quiet_hours_enabled
            ),
            quiet_hours_start=(
                preference.quiet_hours_start
            ),
            quiet_hours_end=(
                preference.quiet_hours_end
            ),
            timezone=preference.timezone,
            allow_urgent_during_quiet_hours=(
                preference
                .allow_urgent_during_quiet_hours
            ),
            allow_critical_during_quiet_hours=(
                preference
                .allow_critical_during_quiet_hours
            ),
            created_at=preference.created_at,
            updated_at=preference.updated_at,
        )

    def _channel_response(
        self,
        channel: AdminNotificationChannel,
    ) -> AdminNotificationChannelResponse:
        return AdminNotificationChannelResponse(
            id=channel.id,
            user_id=channel.user_id,
            channel_type=channel.channel_type,
            is_enabled=channel.is_enabled,
            status=channel.status,
            destination=channel.destination,
            display_name=channel.display_name,
            integration_provider=(
                channel.integration_provider
            ),
            configuration=self._load_dict(
                channel.configuration_json
            ),
            minimum_priority=(
                channel.minimum_priority
            ),
            send_success_notifications=(
                channel.send_success_notifications
            ),
            send_info_notifications=(
                channel.send_info_notifications
            ),
            send_warning_notifications=(
                channel.send_warning_notifications
            ),
            send_error_notifications=(
                channel.send_error_notifications
            ),
            send_critical_notifications=(
                channel.send_critical_notifications
            ),
            last_tested_at=channel.last_tested_at,
            last_test_success=(
                channel.last_test_success
            ),
            last_error=channel.last_error,
            created_at=channel.created_at,
            updated_at=channel.updated_at,
        )

    def get_or_create_preference(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> AdminNotificationPreference:
        preference = (
            admin_notification_preference_repository
            .get_preference(
                db,
                user_id=user_id,
            )
        )

        if preference is not None:
            return preference

        preference = AdminNotificationPreference(
            user_id=user_id,
            is_enabled=True,
            minimum_priority="normal",
            digest_mode="immediate",
            enabled_sources_json=(
                self._dump_json(
                    self.DEFAULT_SOURCES
                )
            ),
            enabled_types_json=(
                self._dump_json(
                    self.DEFAULT_TYPES
                )
            ),
            quiet_hours_enabled=False,
            timezone="America/Mexico_City",
            allow_urgent_during_quiet_hours=True,
            allow_critical_during_quiet_hours=True,
        )

        db.add(preference)
        db.commit()
        db.refresh(preference)

        return preference

    def get_settings(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> AdminNotificationSettingsResponse:
        preference = self.get_or_create_preference(
            db,
            user_id=user_id,
        )

        channels = (
            admin_notification_preference_repository
            .list_channels(
                db,
                user_id=user_id,
            )
        )

        return AdminNotificationSettingsResponse(
            preference=(
                self._preference_response(
                    preference
                )
            ),
            channels=[
                self._channel_response(channel)
                for channel in channels
            ],
        )

    def update_preference(
        self,
        db: Session,
        *,
        user_id: int,
        data: AdminNotificationPreferenceUpdate,
    ) -> AdminNotificationPreferenceResponse:
        preference = self.get_or_create_preference(
            db,
            user_id=user_id,
        )

        minimum_priority = (
            self._validate_priority(
                data.minimum_priority
            )
        )

        digest_mode = (
            self._validate_digest_mode(
                data.digest_mode
            )
        )

        enabled_sources = (
            self._validate_sources(
                data.enabled_sources
            )
        )

        enabled_types = (
            self._validate_types(
                data.enabled_types
            )
        )

        timezone_name = (
            self._validate_timezone(
                data.timezone
            )
        )

        if (
            data.quiet_hours_enabled
            and (
                data.quiet_hours_start is None
                or data.quiet_hours_end is None
            )
        ):
            raise ConflictException(
                "Quiet hours require a start and end time."
            )

        preference.is_enabled = (
            data.is_enabled
        )

        preference.minimum_priority = (
            minimum_priority
        )

        preference.digest_mode = digest_mode

        preference.enabled_sources_json = (
            self._dump_json(
                enabled_sources
            )
        )

        preference.enabled_types_json = (
            self._dump_json(
                enabled_types
            )
        )

        preference.quiet_hours_enabled = (
            data.quiet_hours_enabled
        )

        preference.quiet_hours_start = (
            data.quiet_hours_start
        )

        preference.quiet_hours_end = (
            data.quiet_hours_end
        )

        preference.timezone = timezone_name

        preference.allow_urgent_during_quiet_hours = (
            data.allow_urgent_during_quiet_hours
        )

        preference.allow_critical_during_quiet_hours = (
            data.allow_critical_during_quiet_hours
        )

        db.add(preference)
        db.commit()
        db.refresh(preference)

        return self._preference_response(
            preference
        )

    def create_channel(
        self,
        db: Session,
        *,
        user_id: int,
        data: AdminNotificationChannelCreate,
    ) -> AdminNotificationChannelResponse:
        channel_type = (
            data.channel_type.strip().lower()
        )

        if channel_type not in self.VALID_CHANNELS:
            raise ConflictException(
                "Invalid notification channel."
            )

        existing = (
            admin_notification_preference_repository
            .get_channel(
                db,
                user_id=user_id,
                channel_type=channel_type,
            )
        )

        if existing is not None:
            raise ConflictException(
                "This notification channel already exists."
            )

        minimum_priority = (
            self._validate_priority(
                data.minimum_priority
            )
        )

        destination = (
            data.destination.strip()
            if data.destination
            else None
        )

        self._validate_channel_destination(
            channel_type=channel_type,
            destination=destination,
        )

        channel = AdminNotificationChannel(
            user_id=user_id,
            channel_type=channel_type,
            is_enabled=data.is_enabled,
            status=(
                NotificationChannelStatus.ACTIVE.value
            ),
            destination=destination,
            display_name=data.display_name,
            integration_provider=(
                data.integration_provider
            ),
            configuration_json=(
                self._dump_json(
                    data.configuration
                )
            ),
            minimum_priority=minimum_priority,
            send_success_notifications=(
                data.send_success_notifications
            ),
            send_info_notifications=(
                data.send_info_notifications
            ),
            send_warning_notifications=(
                data.send_warning_notifications
            ),
            send_error_notifications=(
                data.send_error_notifications
            ),
            send_critical_notifications=(
                data.send_critical_notifications
            ),
        )

        db.add(channel)
        db.commit()
        db.refresh(channel)

        return self._channel_response(
            channel
        )

    def update_channel(
        self,
        db: Session,
        *,
        user_id: int,
        channel_id: int,
        data: AdminNotificationChannelUpdate,
    ) -> AdminNotificationChannelResponse:
        channel = (
            admin_notification_preference_repository
            .get_channel_by_id(
                db,
                user_id=user_id,
                channel_id=channel_id,
            )
        )

        if channel is None:
            raise NotFoundException(
                "Notification channel not found."
            )

        if data.is_enabled is not None:
            channel.is_enabled = data.is_enabled

        if data.destination is not None:
            destination = data.destination.strip()

            self._validate_channel_destination(
                channel_type=channel.channel_type,
                destination=destination,
            )

            channel.destination = destination

        if data.display_name is not None:
            channel.display_name = (
                data.display_name
            )

        if data.integration_provider is not None:
            channel.integration_provider = (
                data.integration_provider
            )

        if data.configuration is not None:
            channel.configuration_json = (
                self._dump_json(
                    data.configuration
                )
            )

        if data.minimum_priority is not None:
            channel.minimum_priority = (
                self._validate_priority(
                    data.minimum_priority
                )
            )

        if (
            data.send_success_notifications
            is not None
        ):
            channel.send_success_notifications = (
                data.send_success_notifications
            )

        if (
            data.send_info_notifications
            is not None
        ):
            channel.send_info_notifications = (
                data.send_info_notifications
            )

        if (
            data.send_warning_notifications
            is not None
        ):
            channel.send_warning_notifications = (
                data.send_warning_notifications
            )

        if (
            data.send_error_notifications
            is not None
        ):
            channel.send_error_notifications = (
                data.send_error_notifications
            )

        if (
            data.send_critical_notifications
            is not None
        ):
            channel.send_critical_notifications = (
                data.send_critical_notifications
            )

        channel.status = (
            NotificationChannelStatus.ACTIVE.value
            if channel.is_enabled
            else NotificationChannelStatus.DISABLED.value
        )

        channel.last_error = None

        db.add(channel)
        db.commit()
        db.refresh(channel)

        return self._channel_response(
            channel
        )

    def delete_channel(
        self,
        db: Session,
        *,
        user_id: int,
        channel_id: int,
    ) -> None:
        channel = (
            admin_notification_preference_repository
            .get_channel_by_id(
                db,
                user_id=user_id,
                channel_id=channel_id,
            )
        )

        if channel is None:
            raise NotFoundException(
                "Notification channel not found."
            )

        db.delete(channel)
        db.commit()

    def _is_quiet_hours(
        self,
        *,
        preference: AdminNotificationPreference,
        created_at: datetime,
    ) -> bool:
        if not preference.quiet_hours_enabled:
            return False

        if (
            preference.quiet_hours_start is None
            or preference.quiet_hours_end is None
        ):
            return False

        timezone_info = ZoneInfo(
            preference.timezone
        )

        normalized_datetime = created_at

        if normalized_datetime.tzinfo is None:
            normalized_datetime = (
                normalized_datetime.replace(
                    tzinfo=timezone.utc
                )
            )

        local_time = (
            normalized_datetime
            .astimezone(timezone_info)
            .time()
            .replace(tzinfo=None)
        )

        start = preference.quiet_hours_start
        end = preference.quiet_hours_end

        if start == end:
            return True

        if start < end:
            return start <= local_time < end

        return (
            local_time >= start
            or local_time < end
        )

    def _channel_allows_type(
        self,
        channel: AdminNotificationChannel,
        notification_type: str,
    ) -> bool:
        mapping = {
            "success": (
                channel.send_success_notifications
            ),
            "info": (
                channel.send_info_notifications
            ),
            "warning": (
                channel.send_warning_notifications
            ),
            "error": (
                channel.send_error_notifications
            ),
            "critical": (
                channel.send_critical_notifications
            ),
        }

        return bool(
            mapping.get(
                notification_type,
                False,
            )
        )

    def preview_routing(
        self,
        db: Session,
        *,
        user_id: int,
        data: NotificationRoutingPreviewRequest,
    ) -> NotificationRoutingPreviewResponse:
        preference = self.get_or_create_preference(
            db,
            user_id=user_id,
        )

        channels = (
            admin_notification_preference_repository
            .list_channels(
                db,
                user_id=user_id,
            )
        )

        notification_type = (
            data.notification_type
            .strip()
            .lower()
        )

        priority = (
            self._validate_priority(
                data.priority
            )
        )

        source = data.source.strip().lower()

        created_at = (
            data.created_at
            or datetime.now(timezone.utc)
        )

        quiet_hours = self._is_quiet_hours(
            preference=preference,
            created_at=created_at,
        )

        enabled_sources = self._load_list(
            preference.enabled_sources_json,
            default=self.DEFAULT_SOURCES,
        )

        enabled_types = self._load_list(
            preference.enabled_types_json,
            default=self.DEFAULT_TYPES,
        )

        globally_allowed = True
        global_reason = "Allowed."

        if not preference.is_enabled:
            globally_allowed = False
            global_reason = (
                "Notifications are disabled."
            )

        elif source not in enabled_sources:
            globally_allowed = False
            global_reason = (
                "The notification source is disabled."
            )

        elif notification_type not in enabled_types:
            globally_allowed = False
            global_reason = (
                "The notification type is disabled."
            )

        elif (
            self.PRIORITY_RANK.get(
                priority,
                0,
            )
            <
            self.PRIORITY_RANK.get(
                preference.minimum_priority,
                0,
            )
        ):
            globally_allowed = False
            global_reason = (
                "The notification priority is below "
                "the configured minimum."
            )

        elif quiet_hours:
            critical_allowed = (
                notification_type == "critical"
                and preference
                .allow_critical_during_quiet_hours
            )

            urgent_allowed = (
                priority == "urgent"
                and preference
                .allow_urgent_during_quiet_hours
            )

            if not (
                critical_allowed
                or urgent_allowed
            ):
                globally_allowed = False
                global_reason = (
                    "The notification falls within "
                    "quiet hours."
                )

        results: list[
            NotificationRoutingPreviewChannel
        ] = []

        selected_channels: list[str] = []

        for channel in channels:
            selected = globally_allowed
            reason = global_reason

            if selected and not channel.is_enabled:
                selected = False
                reason = "Channel is disabled."

            elif (
                selected
                and channel.status
                != NotificationChannelStatus.ACTIVE.value
            ):
                selected = False
                reason = (
                    "Channel is not active."
                )

            elif (
                selected
                and self.PRIORITY_RANK.get(
                    priority,
                    0,
                )
                <
                self.PRIORITY_RANK.get(
                    channel.minimum_priority,
                    0,
                )
            ):
                selected = False
                reason = (
                    "Priority is below the channel minimum."
                )

            elif (
                selected
                and not self._channel_allows_type(
                    channel,
                    notification_type,
                )
            ):
                selected = False
                reason = (
                    "The channel does not accept this "
                    "notification type."
                )

            if selected:
                reason = "Selected for delivery."
                selected_channels.append(
                    channel.channel_type
                )

            results.append(
                NotificationRoutingPreviewChannel(
                    channel_type=(
                        channel.channel_type
                    ),
                    selected=selected,
                    reason=reason,
                )
            )

        return NotificationRoutingPreviewResponse(
            will_notify=bool(
                selected_channels
            ),
            is_quiet_hours=quiet_hours,
            selected_channels=(
                selected_channels
            ),
            channels=results,
        )


admin_notification_preference_service = (
    AdminNotificationPreferenceService()
)