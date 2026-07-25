import json
import smtplib
import ssl
from email.message import EmailMessage

from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.time import utc_now
from app.core.config import settings
from app.models.user import User
from app.models.user_notification import (
    UserNotification,
)
from app.models.user_push_subscription import (
    UserPushSubscription,
)
from app.services.user_notification_preference_service import (
    user_notification_preference_service,
)


class UserNotificationDeliveryService:
    PRIORITY_RANK = {
        "low": 1,
        "normal": 2,
        "high": 3,
        "urgent": 4,
    }

    def _channel_allowed(
        self,
        *,
        notification: UserNotification,
        minimum_priority: str,
    ) -> bool:
        return (
            self.PRIORITY_RANK.get(
                notification.priority,
                0,
            )
            >= self.PRIORITY_RANK.get(
                minimum_priority,
                0,
            )
        )

    def _send_email(
        self,
        *,
        user: User,
        notification: UserNotification,
    ) -> None:
        smtp_host = getattr(
            settings,
            "SMTP_HOST",
            "",
        )

        smtp_port = int(
            getattr(
                settings,
                "SMTP_PORT",
                587,
            )
        )

        smtp_username = getattr(
            settings,
            "SMTP_USERNAME",
            "",
        )

        smtp_password = getattr(
            settings,
            "SMTP_PASSWORD",
            "",
        )

        smtp_from_email = getattr(
            settings,
            "SMTP_FROM_EMAIL",
            "",
        )

        smtp_from_name = getattr(
            settings,
            "SMTP_FROM_NAME",
            "AI Virtual Try-On",
        )

        if not smtp_host or not smtp_from_email:
            raise RuntimeError(
                "SMTP is not configured."
            )

        destination = getattr(
            user,
            "email",
            None,
        )

        if not destination:
            raise RuntimeError(
                "User has no email address."
            )

        message = EmailMessage()
        message["Subject"] = notification.title
        message["From"] = (
            f"{smtp_from_name} "
            f"<{smtp_from_email}>"
        )
        message["To"] = destination

        content = notification.message

        if notification.action_url:
            content += (
                "\n\n"
                + (
                    notification.action_label
                    or "Open"
                )
                + "\n"
                + notification.action_url
            )

        message.set_content(content)

        use_ssl = bool(
            getattr(
                settings,
                "SMTP_USE_SSL",
                False,
            )
        )

        use_tls = bool(
            getattr(
                settings,
                "SMTP_USE_TLS",
                True,
            )
        )

        context = ssl.create_default_context()

        if use_ssl:
            server: smtplib.SMTP = (
                smtplib.SMTP_SSL(
                    smtp_host,
                    smtp_port,
                    timeout=20,
                    context=context,
                )
            )
        else:
            server = smtplib.SMTP(
                smtp_host,
                smtp_port,
                timeout=20,
            )

        try:
            if use_tls and not use_ssl:
                server.starttls(
                    context=context
                )

            if smtp_username:
                server.login(
                    smtp_username,
                    smtp_password,
                )

            server.send_message(message)

        finally:
            try:
                server.quit()
            except Exception:
                pass

    def _send_web_push(
        self,
        db: Session,
        *,
        user_id: int,
        notification: UserNotification,
    ) -> int:
        private_key = getattr(
            settings,
            "WEB_PUSH_VAPID_PRIVATE_KEY",
            "",
        )

        subject = getattr(
            settings,
            "WEB_PUSH_VAPID_SUBJECT",
            "",
        )

        if not private_key or not subject:
            raise RuntimeError(
                "Web Push VAPID is not configured."
            )

        subscriptions = list(
            db.execute(
                select(
                    UserPushSubscription
                ).where(
                    UserPushSubscription.user_id
                    == user_id,
                    UserPushSubscription.is_active.is_(
                        True
                    ),
                )
            ).scalars().all()
        )

        payload = json.dumps(
            {
                "notification_id": notification.id,
                "title": notification.title,
                "body": notification.message,
                "icon": "/icons/icon-192.png",
                "badge": "/icons/badge-72.png",
                "image": notification.image_url,
                "url": notification.action_url,
                "action_label": (
                    notification.action_label
                ),
                "type": (
                    notification.notification_type
                ),
                "priority": notification.priority,
            },
            ensure_ascii=False,
            default=str,
        )

        delivered = 0

        for subscription in subscriptions:
            subscription.last_used_at = utc_now()

            try:
                webpush(
                    subscription_info={
                        "endpoint": (
                            subscription.endpoint
                        ),
                        "keys": {
                            "p256dh": (
                                subscription.p256dh_key
                            ),
                            "auth": (
                                subscription.auth_key
                            ),
                        },
                    },
                    data=payload,
                    vapid_private_key=private_key,
                    vapid_claims={
                        "sub": subject,
                    },
                    ttl=3600,
                )

                subscription.failure_count = 0
                subscription.last_success_at = (
                    utc_now()
                )
                subscription.last_error = None

                delivered += 1

            except WebPushException as error:
                subscription.failure_count += 1
                subscription.last_failure_at = (
                    utc_now()
                )
                subscription.last_error = str(error)

                response = getattr(
                    error,
                    "response",
                    None,
                )

                status_code = getattr(
                    response,
                    "status_code",
                    None,
                )

                if status_code in {
                    404,
                    410,
                }:
                    subscription.is_active = False

                elif subscription.failure_count >= 5:
                    subscription.is_active = False

            db.add(subscription)

        db.commit()

        return delivered

    def deliver(
        self,
        db: Session,
        *,
        notification: UserNotification,
    ) -> dict:
        if notification.recipient_user_id is None:
            return {
                "in_app": True,
                "email": False,
                "web_push": False,
                "reason": (
                    "Global announcements are "
                    "delivered in-app."
                ),
            }

        user = db.get(
            User,
            notification.recipient_user_id,
        )

        if user is None:
            return {
                "in_app": False,
                "email": False,
                "web_push": False,
                "reason": "User not found.",
            }

        preference = (
            user_notification_preference_service
            .get_or_create(
                db,
                user_id=user.id,
            )
        )

        if not (
            user_notification_preference_service
            .source_is_enabled(
                preference,
                source=notification.source,
            )
        ):
            return {
                "in_app": False,
                "email": False,
                "web_push": False,
                "reason": (
                    "Notification source disabled."
                ),
            }

        if not (
            user_notification_preference_service
            .event_is_enabled(
                preference,
                event_type=notification.event_type,
            )
        ):
            return {
                "in_app": False,
                "email": False,
                "web_push": False,
                "reason": (
                    "Notification event disabled."
                ),
            }

        quiet_hours = (
            user_notification_preference_service
            .is_quiet_hours(preference)
        )

        urgent_override = (
            notification.priority == "urgent"
            and preference
            .allow_urgent_during_quiet_hours
        )

        external_channels_allowed = (
            not quiet_hours
            or urgent_override
        )

        email_delivered = False
        web_push_delivered = False
        errors: list[str] = []

        if (
            external_channels_allowed
            and preference.email_enabled
            and bool(
                getattr(
                    settings,
                    "USER_NOTIFICATION_EMAIL_ENABLED",
                    True,
                )
            )
            and self._channel_allowed(
                notification=notification,
                minimum_priority=(
                    preference
                    .email_minimum_priority
                ),
            )
        ):
            try:
                self._send_email(
                    user=user,
                    notification=notification,
                )

                email_delivered = True

            except Exception as error:
                errors.append(
                    "email: " + str(error)
                )

        if (
            external_channels_allowed
            and preference.web_push_enabled
            and bool(
                getattr(
                    settings,
                    "USER_NOTIFICATION_WEB_PUSH_ENABLED",
                    True,
                )
            )
            and self._channel_allowed(
                notification=notification,
                minimum_priority=(
                    preference
                    .web_push_minimum_priority
                ),
            )
        ):
            try:
                delivered_count = (
                    self._send_web_push(
                        db,
                        user_id=user.id,
                        notification=notification,
                    )
                )

                web_push_delivered = (
                    delivered_count > 0
                )

            except Exception as error:
                errors.append(
                    "web_push: " + str(error)
                )

        return {
            "in_app": preference.in_app_enabled,
            "email": email_delivered,
            "web_push": web_push_delivered,
            "quiet_hours": quiet_hours,
            "errors": errors,
        }


user_notification_delivery_service = (
    UserNotificationDeliveryService()
)