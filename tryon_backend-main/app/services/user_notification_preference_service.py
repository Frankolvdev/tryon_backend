import hashlib
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.exceptions import (
    ConflictException,
    NotFoundException,
)
from app.common.time import utc_now
from app.models.user_notification_preference import (
    UserNotificationPreference,
)
from app.models.user_push_subscription import (
    UserPushSubscription,
)
from app.schemas.user_notification_preference import (
    UserNotificationPreferenceResponse,
    UserNotificationPreferenceUpdate,
    UserPushSubscriptionCreate,
    UserPushSubscriptionResponse,
)


class UserNotificationPreferenceService:
    PRIORITY_RANK = {
        "low": 1,
        "normal": 2,
        "high": 3,
        "urgent": 4,
    }

    def _dump_list(
        self,
        value: list[str],
    ) -> str:
        return json.dumps(
            sorted(set(value)),
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def _load_list(
        self,
        value: str | None,
    ) -> list[str]:
        if not value:
            return []

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

        return []

    def _validate_priority(
        self,
        value: str,
    ) -> str:
        normalized = value.strip().lower()

        if normalized not in self.PRIORITY_RANK:
            raise ConflictException(
                "Invalid notification priority."
            )

        return normalized

    def _validate_timezone(
        self,
        value: str,
    ) -> str:
        try:
            ZoneInfo(value)

        except ZoneInfoNotFoundError as error:
            raise ConflictException(
                "Invalid IANA timezone."
            ) from error

        return value

    def _response(
        self,
        preference: UserNotificationPreference,
    ) -> UserNotificationPreferenceResponse:
        return UserNotificationPreferenceResponse(
            id=preference.id,
            user_id=preference.user_id,
            in_app_enabled=preference.in_app_enabled,
            email_enabled=preference.email_enabled,
            web_push_enabled=preference.web_push_enabled,
            marketing_enabled=preference.marketing_enabled,
            tryon_notifications_enabled=(
                preference.tryon_notifications_enabled
            ),
            billing_notifications_enabled=(
                preference.billing_notifications_enabled
            ),
            token_notifications_enabled=(
                preference.token_notifications_enabled
            ),
            subscription_notifications_enabled=(
                preference.subscription_notifications_enabled
            ),
            support_notifications_enabled=(
                preference.support_notifications_enabled
            ),
            security_notifications_enabled=(
                preference.security_notifications_enabled
            ),
            announcement_notifications_enabled=(
                preference.announcement_notifications_enabled
            ),
            minimum_priority=preference.minimum_priority,
            email_minimum_priority=(
                preference.email_minimum_priority
            ),
            web_push_minimum_priority=(
                preference.web_push_minimum_priority
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
                preference.allow_urgent_during_quiet_hours
            ),
            disabled_event_types=self._load_list(
                preference.disabled_event_types_json
            ),
            created_at=preference.created_at,
            updated_at=preference.updated_at,
        )

    def get_or_create(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> UserNotificationPreference:
        preference = db.execute(
            select(
                UserNotificationPreference
            ).where(
                UserNotificationPreference.user_id
                == user_id
            )
        ).scalar_one_or_none()

        if preference is not None:
            return preference

        preference = UserNotificationPreference(
            user_id=user_id,
        )

        db.add(preference)
        db.commit()
        db.refresh(preference)

        return preference

    def get_response(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> UserNotificationPreferenceResponse:
        return self._response(
            self.get_or_create(
                db,
                user_id=user_id,
            )
        )

    def update(
        self,
        db: Session,
        *,
        user_id: int,
        data: UserNotificationPreferenceUpdate,
    ) -> UserNotificationPreferenceResponse:
        preference = self.get_or_create(
            db,
            user_id=user_id,
        )

        if (
            data.quiet_hours_enabled
            and (
                data.quiet_hours_start is None
                or data.quiet_hours_end is None
            )
        ):
            raise ConflictException(
                "Quiet hours require start and end times."
            )

        preference.in_app_enabled = (
            data.in_app_enabled
        )

        preference.email_enabled = (
            data.email_enabled
        )

        preference.web_push_enabled = (
            data.web_push_enabled
        )

        preference.marketing_enabled = (
            data.marketing_enabled
        )

        preference.tryon_notifications_enabled = (
            data.tryon_notifications_enabled
        )

        preference.billing_notifications_enabled = (
            data.billing_notifications_enabled
        )

        preference.token_notifications_enabled = (
            data.token_notifications_enabled
        )

        preference.subscription_notifications_enabled = (
            data.subscription_notifications_enabled
        )

        preference.support_notifications_enabled = (
            data.support_notifications_enabled
        )

        preference.security_notifications_enabled = (
            data.security_notifications_enabled
        )

        preference.announcement_notifications_enabled = (
            data.announcement_notifications_enabled
        )

        preference.minimum_priority = (
            self._validate_priority(
                data.minimum_priority
            )
        )

        preference.email_minimum_priority = (
            self._validate_priority(
                data.email_minimum_priority
            )
        )

        preference.web_push_minimum_priority = (
            self._validate_priority(
                data.web_push_minimum_priority
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

        preference.timezone = (
            self._validate_timezone(
                data.timezone
            )
        )

        preference.allow_urgent_during_quiet_hours = (
            data.allow_urgent_during_quiet_hours
        )

        preference.disabled_event_types_json = (
            self._dump_list(
                data.disabled_event_types
            )
        )

        db.add(preference)
        db.commit()
        db.refresh(preference)

        return self._response(preference)

    def source_is_enabled(
        self,
        preference: UserNotificationPreference,
        *,
        source: str,
    ) -> bool:
        mapping = {
            "tryon": (
                preference.tryon_notifications_enabled
            ),
            "billing": (
                preference.billing_notifications_enabled
            ),
            "tokens": (
                preference.token_notifications_enabled
            ),
            "subscription": (
                preference.subscription_notifications_enabled
            ),
            "support": (
                preference.support_notifications_enabled
            ),
            "security": (
                preference.security_notifications_enabled
            ),
            "announcement": (
                preference.announcement_notifications_enabled
            ),
            "system": True,
        }

        return bool(
            mapping.get(
                source,
                True,
            )
        )

    def event_is_enabled(
        self,
        preference: UserNotificationPreference,
        *,
        event_type: str | None,
    ) -> bool:
        if not event_type:
            return True

        disabled = self._load_list(
            preference.disabled_event_types_json
        )

        return event_type not in disabled

    def is_quiet_hours(
        self,
        preference: UserNotificationPreference,
        *,
        checked_at: datetime | None = None,
    ) -> bool:
        if not preference.quiet_hours_enabled:
            return False

        if (
            preference.quiet_hours_start is None
            or preference.quiet_hours_end is None
        ):
            return False

        current = checked_at or utc_now()

        if current.tzinfo is None:
            current = current.replace(
                tzinfo=timezone.utc
            )

        local_time = (
            current
            .astimezone(
                ZoneInfo(
                    preference.timezone
                )
            )
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

    def register_push_subscription(
        self,
        db: Session,
        *,
        user_id: int,
        data: UserPushSubscriptionCreate,
        user_agent: str | None,
    ) -> UserPushSubscriptionResponse:
        endpoint_hash = hashlib.sha256(
            data.endpoint.encode("utf-8")
        ).hexdigest()

        subscription = db.execute(
            select(
                UserPushSubscription
            ).where(
                UserPushSubscription.endpoint_hash
                == endpoint_hash
            )
        ).scalar_one_or_none()

        if subscription is None:
            subscription = UserPushSubscription(
                user_id=user_id,
                endpoint=data.endpoint,
                endpoint_hash=endpoint_hash,
                p256dh_key=data.p256dh_key,
                auth_key=data.auth_key,
            )

        subscription.user_id = user_id
        subscription.endpoint = data.endpoint
        subscription.p256dh_key = data.p256dh_key
        subscription.auth_key = data.auth_key
        subscription.user_agent = user_agent
        subscription.device_name = data.device_name
        subscription.is_active = True
        subscription.failure_count = 0
        subscription.last_error = None

        db.add(subscription)
        db.commit()
        db.refresh(subscription)

        return self._push_response(
            subscription
        )

    def _push_response(
        self,
        subscription: UserPushSubscription,
    ) -> UserPushSubscriptionResponse:
        return UserPushSubscriptionResponse(
            id=subscription.id,
            device_name=subscription.device_name,
            is_active=subscription.is_active,
            failure_count=subscription.failure_count,
            last_used_at=subscription.last_used_at,
            last_success_at=subscription.last_success_at,
            last_failure_at=subscription.last_failure_at,
            created_at=subscription.created_at,
            updated_at=subscription.updated_at,
        )

    def list_push_subscriptions(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> list[UserPushSubscriptionResponse]:
        subscriptions = list(
            db.execute(
                select(
                    UserPushSubscription
                )
                .where(
                    UserPushSubscription.user_id
                    == user_id
                )
                .order_by(
                    UserPushSubscription.created_at.desc()
                )
            ).scalars().all()
        )

        return [
            self._push_response(item)
            for item in subscriptions
        ]

    def remove_push_subscription(
        self,
        db: Session,
        *,
        user_id: int,
        subscription_id: int,
    ) -> None:
        subscription = db.execute(
            select(
                UserPushSubscription
            ).where(
                UserPushSubscription.id
                == subscription_id,
                UserPushSubscription.user_id
                == user_id,
            )
        ).scalar_one_or_none()

        if subscription is None:
            raise NotFoundException(
                "Push subscription not found."
            )

        db.delete(subscription)
        db.commit()


user_notification_preference_service = (
    UserNotificationPreferenceService()
)