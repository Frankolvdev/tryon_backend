import json
import smtplib
import ssl
from datetime import timedelta
from email.message import EmailMessage
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.common.exceptions import (
    ConflictException,
    NotFoundException,
)
from app.common.notification_delivery_status import (
    NotificationDeliveryStatus,
)
from app.common.time import utc_now
from app.core.config import settings
from app.models.admin_notification import (
    AdminNotification,
)
from app.models.admin_notification_channel import (
    AdminNotificationChannel,
)
from app.models.admin_notification_delivery import (
    AdminNotificationDelivery,
)
from app.repositories.admin_notification_delivery_repository import (
    admin_notification_delivery_repository,
)
from app.repositories.admin_notification_preference_repository import (
    admin_notification_preference_repository,
)
from app.schemas.admin_notification_delivery import (
    AdminNotificationDeliveryListResponse,
    AdminNotificationDeliveryResponse,
)
from app.services.operational_event_service import (
    operational_event_service,
)


class AdminNotificationDeliveryService:
    RETRY_DELAYS_SECONDS = (
        60,
        300,
        900,
        3600,
        21600,
    )

    def _parse_json(
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

    def _dump_json(
        self,
        value: dict[str, Any],
    ) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        )

    def _masked_destination(
        self,
        channel_type: str,
        destination: str | None,
    ) -> str | None:
        if not destination:
            return None

        if channel_type == "email":
            local, separator, domain = (
                destination.partition("@")
            )

            if not separator:
                return destination

            visible = local[:2]

            return (
                visible
                + "***@"
                + domain
            )

        if channel_type == "webhook":
            return "[HTTPS WEBHOOK]"

        if len(destination) <= 6:
            return "***"

        return (
            destination[:3]
            + "***"
            + destination[-3:]
        )

    def _response(
        self,
        delivery: AdminNotificationDelivery,
    ) -> AdminNotificationDeliveryResponse:
        return AdminNotificationDeliveryResponse(
            id=delivery.id,
            notification_id=(
                delivery.notification_id
            ),
            channel_id=delivery.channel_id,
            recipient_user_id=(
                delivery.recipient_user_id
            ),
            channel_type=delivery.channel_type,
            destination=self._masked_destination(
                delivery.channel_type,
                delivery.destination,
            ),
            status=delivery.status,
            attempt_count=delivery.attempt_count,
            max_attempts=delivery.max_attempts,
            provider_message_id=(
                delivery.provider_message_id
            ),
            provider_status_code=(
                delivery.provider_status_code
            ),
            error_type=delivery.error_type,
            error_message=delivery.error_message,
            provider_response=self._parse_json(
                delivery.provider_response_json
            ),
            scheduled_at=delivery.scheduled_at,
            processing_started_at=(
                delivery.processing_started_at
            ),
            delivered_at=delivery.delivered_at,
            failed_at=delivery.failed_at,
            next_retry_at=delivery.next_retry_at,
            created_at=delivery.created_at,
            updated_at=delivery.updated_at,
        )

    def _create_delivery(
        self,
        db: Session,
        *,
        notification: AdminNotification,
        channel: AdminNotificationChannel,
    ) -> AdminNotificationDelivery:
        delivery = AdminNotificationDelivery(
            notification_id=notification.id,
            channel_id=channel.id,
            recipient_user_id=(
                channel.user_id
            ),
            channel_type=channel.channel_type,
            destination=channel.destination,
            status=(
                NotificationDeliveryStatus
                .PENDING
                .value
            ),
            attempt_count=0,
            max_attempts=int(
                getattr(
                    settings,
                    "NOTIFICATION_MAX_ATTEMPTS",
                    5,
                )
            ),
            scheduled_at=utc_now(),
        )

        db.add(delivery)
        db.commit()
        db.refresh(delivery)

        return delivery

    def _message_payload(
        self,
        notification: AdminNotification,
    ) -> dict[str, Any]:
        return {
            "id": notification.id,
            "type": notification.notification_type,
            "priority": notification.priority,
            "source": notification.source,
            "event_type": notification.event_type,
            "title": notification.title,
            "message": notification.message,
            "action_url": notification.action_url,
            "action_label": notification.action_label,
            "entity_type": notification.entity_type,
            "entity_id": notification.entity_id,
            "correlation_id": (
                notification.correlation_id
            ),
            "created_at": (
                notification.created_at.isoformat()
            ),
            "metadata": self._parse_json(
                notification.metadata_json
            ),
        }

    def _send_backoffice(
        self,
        *,
        notification: AdminNotification,
        channel: AdminNotificationChannel,
    ) -> dict[str, Any]:
        del channel

        return {
            "success": True,
            "provider_message_id": (
                f"backoffice:{notification.id}"
            ),
            "status_code": 200,
            "response": {
                "stored": True,
            },
        }

    def _send_email(
        self,
        *,
        notification: AdminNotification,
        channel: AdminNotificationChannel,
    ) -> dict[str, Any]:
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

        from_email = getattr(
            settings,
            "SMTP_FROM_EMAIL",
            "",
        )

        from_name = getattr(
            settings,
            "SMTP_FROM_NAME",
            "AI Virtual Try-On",
        )

        use_tls = bool(
            getattr(
                settings,
                "SMTP_USE_TLS",
                True,
            )
        )

        use_ssl = bool(
            getattr(
                settings,
                "SMTP_USE_SSL",
                False,
            )
        )

        if not smtp_host or not from_email:
            raise ConflictException(
                "SMTP is not configured."
            )

        if not channel.destination:
            raise ConflictException(
                "Email destination is missing."
            )

        message = EmailMessage()

        message["Subject"] = notification.title
        message["From"] = (
            f"{from_name} <{from_email}>"
        )
        message["To"] = channel.destination

        body_lines = [
            notification.message,
        ]

        if notification.action_url:
            body_lines.extend(
                [
                    "",
                    (
                        notification.action_label
                        or "Open notification"
                    ),
                    notification.action_url,
                ]
            )

        message.set_content(
            "\n".join(body_lines)
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

        return {
            "success": True,
            "provider_message_id": None,
            "status_code": 250,
            "response": {
                "accepted": True,
            },
        }

    def _send_telegram(
        self,
        *,
        notification: AdminNotification,
        channel: AdminNotificationChannel,
    ) -> dict[str, Any]:
        token = getattr(
            settings,
            "TELEGRAM_BOT_TOKEN",
            "",
        )

        if not token:
            raise ConflictException(
                "Telegram bot token is not configured."
            )

        if not channel.destination:
            raise ConflictException(
                "Telegram chat ID is missing."
            )

        text = (
            f"<b>{notification.title}</b>\n\n"
            f"{notification.message}"
        )

        if notification.action_url:
            text += (
                "\n\n"
                f'<a href="{notification.action_url}">'
                f"{notification.action_label or 'Open'}"
                "</a>"
            )

        url = (
            "https://api.telegram.org/bot"
            f"{token}/sendMessage"
        )

        timeout = float(
            getattr(
                settings,
                "NOTIFICATION_HTTP_TIMEOUT_SECONDS",
                20,
            )
        )

        with httpx.Client(
            timeout=timeout
        ) as client:
            response = client.post(
                url,
                json={
                    "chat_id": channel.destination,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )

        response.raise_for_status()

        payload = response.json()

        result = payload.get(
            "result",
            {},
        )

        return {
            "success": bool(
                payload.get("ok")
            ),
            "provider_message_id": str(
                result.get("message_id")
            )
            if result.get("message_id")
            is not None
            else None,
            "status_code": response.status_code,
            "response": {
                "ok": payload.get("ok"),
            },
        }

    def _send_slack(
        self,
        *,
        notification: AdminNotification,
        channel: AdminNotificationChannel,
    ) -> dict[str, Any]:
        webhook_url = getattr(
            settings,
            "SLACK_WEBHOOK_URL",
            "",
        )

        bot_token = getattr(
            settings,
            "SLACK_BOT_TOKEN",
            "",
        )

        timeout = float(
            getattr(
                settings,
                "NOTIFICATION_HTTP_TIMEOUT_SECONDS",
                20,
            )
        )

        text = (
            f"*{notification.title}*\n"
            f"{notification.message}"
        )

        if notification.action_url:
            text += (
                "\n<"
                f"{notification.action_url}|"
                f"{notification.action_label or 'Open'}"
                ">"
            )

        with httpx.Client(
            timeout=timeout
        ) as client:
            if webhook_url:
                response = client.post(
                    webhook_url,
                    json={
                        "text": text,
                    },
                )

                response.raise_for_status()

                return {
                    "success": True,
                    "provider_message_id": None,
                    "status_code": (
                        response.status_code
                    ),
                    "response": {
                        "text": response.text[:500],
                    },
                }

            if not bot_token:
                raise ConflictException(
                    "Slack is not configured."
                )

            if not channel.destination:
                raise ConflictException(
                    "Slack channel destination is missing."
                )

            response = client.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": (
                        f"Bearer {bot_token}"
                    ),
                },
                json={
                    "channel": channel.destination,
                    "text": text,
                },
            )

        response.raise_for_status()

        payload = response.json()

        if not payload.get("ok"):
            raise ConflictException(
                str(
                    payload.get(
                        "error",
                        "Slack delivery failed.",
                    )
                )
            )

        return {
            "success": True,
            "provider_message_id": payload.get(
                "ts"
            ),
            "status_code": response.status_code,
            "response": {
                "ok": payload.get("ok"),
                "channel": payload.get("channel"),
            },
        }

    def _send_webhook(
        self,
        *,
        notification: AdminNotification,
        channel: AdminNotificationChannel,
    ) -> dict[str, Any]:
        if not channel.destination:
            raise ConflictException(
                "Webhook destination is missing."
            )

        if not channel.destination.startswith(
            "https://"
        ):
            raise ConflictException(
                "Webhook destination must use HTTPS."
            )

        timeout = float(
            getattr(
                settings,
                "NOTIFICATION_HTTP_TIMEOUT_SECONDS",
                20,
            )
        )

        payload = {
            "event": "admin.notification",
            "notification": self._message_payload(
                notification
            ),
        }

        with httpx.Client(
            timeout=timeout,
            follow_redirects=False,
        ) as client:
            response = client.post(
                channel.destination,
                json=payload,
                headers={
                    "User-Agent": (
                        "TryOn-Notification-Delivery/1.0"
                    ),
                },
            )

        response.raise_for_status()

        return {
            "success": True,
            "provider_message_id": (
                response.headers.get(
                    "x-request-id"
                )
            ),
            "status_code": response.status_code,
            "response": {
                "content_type": (
                    response.headers.get(
                        "content-type"
                    )
                ),
                "body_preview": (
                    response.text[:500]
                ),
            },
        }

    def _send(
        self,
        *,
        notification: AdminNotification,
        channel: AdminNotificationChannel,
    ) -> dict[str, Any]:
        senders = {
            "backoffice": self._send_backoffice,
            "email": self._send_email,
            "telegram": self._send_telegram,
            "slack": self._send_slack,
            "webhook": self._send_webhook,
        }

        sender = senders.get(
            channel.channel_type
        )

        if sender is None:
            raise ConflictException(
                "Unsupported notification channel."
            )

        return sender(
            notification=notification,
            channel=channel,
        )

    def execute_delivery(
        self,
        db: Session,
        *,
        delivery: AdminNotificationDelivery,
    ) -> AdminNotificationDeliveryResponse:
        notification = db.get(
            AdminNotification,
            delivery.notification_id,
        )

        if notification is None:
            raise NotFoundException(
                "Notification not found."
            )

        channel = (
            admin_notification_preference_repository
            .get_channel_by_id(
                db,
                user_id=(
                    delivery.recipient_user_id
                    or 0
                ),
                channel_id=delivery.channel_id or 0,
            )
        )

        if channel is None:
            delivery.status = (
                NotificationDeliveryStatus
                .SKIPPED
                .value
            )
            delivery.error_message = (
                "Notification channel no longer exists."
            )

            db.add(delivery)
            db.commit()
            db.refresh(delivery)

            return self._response(delivery)

        delivery.status = (
            NotificationDeliveryStatus
            .PROCESSING
            .value
        )
        delivery.processing_started_at = utc_now()
        delivery.attempt_count += 1
        delivery.error_type = None
        delivery.error_message = None
        delivery.next_retry_at = None

        db.add(delivery)
        db.commit()
        db.refresh(delivery)

        try:
            result = self._send(
                notification=notification,
                channel=channel,
            )

            delivery.status = (
                NotificationDeliveryStatus
                .DELIVERED
                .value
            )

            delivery.provider_message_id = (
                result.get(
                    "provider_message_id"
                )
            )

            delivery.provider_status_code = (
                result.get("status_code")
            )

            delivery.provider_response_json = (
                self._dump_json(
                    result.get(
                        "response",
                        {},
                    )
                )
            )

            delivery.delivered_at = utc_now()
            delivery.failed_at = None
            delivery.next_retry_at = None

            channel.last_tested_at = utc_now()
            channel.last_test_success = True
            channel.last_error = None

            db.add(channel)
            db.add(delivery)
            db.commit()
            db.refresh(delivery)

            return self._response(delivery)

        except Exception as error:
            now = utc_now()

            delivery.error_type = (
                error.__class__.__name__
            )
            delivery.error_message = str(error)
            delivery.failed_at = now

            if (
                delivery.attempt_count
                < delivery.max_attempts
            ):
                delivery.status = (
                    NotificationDeliveryStatus
                    .RETRYING
                    .value
                )

                retry_index = min(
                    delivery.attempt_count - 1,
                    len(
                        self.RETRY_DELAYS_SECONDS
                    )
                    - 1,
                )

                delivery.next_retry_at = (
                    now
                    + timedelta(
                        seconds=(
                            self.RETRY_DELAYS_SECONDS[
                                retry_index
                            ]
                        )
                    )
                )

            else:
                delivery.status = (
                    NotificationDeliveryStatus
                    .FAILED
                    .value
                )
                delivery.next_retry_at = None

            channel.last_tested_at = now
            channel.last_test_success = False
            channel.last_error = str(error)

            db.add(channel)
            db.add(delivery)
            db.commit()
            db.refresh(delivery)

            operational_event_service.safe_create(
                db,
                event_type=(
                    "admin_notification_delivery_failed"
                ),
                source="notifications",
                severity=(
                    "error"
                    if delivery.status == "failed"
                    else "warning"
                ),
                message=(
                    "An admin notification delivery failed."
                ),
                exception=error,
                details={
                    "delivery_id": delivery.id,
                    "notification_id": (
                        delivery.notification_id
                    ),
                    "channel_type": (
                        delivery.channel_type
                    ),
                    "attempt_count": (
                        delivery.attempt_count
                    ),
                    "max_attempts": (
                        delivery.max_attempts
                    ),
                    "next_retry_at": (
                        delivery.next_retry_at
                    ),
                },
            )

            return self._response(delivery)

    def test_channel(
        self,
        db: Session,
        *,
        user_id: int,
        channel_id: int,
        title: str,
        message: str,
    ) -> AdminNotificationDeliveryResponse:
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

        notification = AdminNotification(
            recipient_user_id=user_id,
            notification_type="info",
            priority="normal",
            source="system",
            event_type="notification_channel_test",
            title=title,
            message=message,
            is_global=False,
            requires_action=False,
        )

        db.add(notification)
        db.commit()
        db.refresh(notification)

        delivery = self._create_delivery(
            db,
            notification=notification,
            channel=channel,
        )

        return self.execute_delivery(
            db,
            delivery=delivery,
        )

    def retry_delivery(
        self,
        db: Session,
        *,
        delivery_id: int,
    ) -> AdminNotificationDeliveryResponse:
        delivery = (
            admin_notification_delivery_repository
            .get_by_id(
                db,
                delivery_id=delivery_id,
            )
        )

        if delivery is None:
            raise NotFoundException(
                "Notification delivery not found."
            )

        if (
            delivery.status
            == NotificationDeliveryStatus
            .DELIVERED
            .value
        ):
            raise ConflictException(
                "The delivery already succeeded."
            )

        if (
            delivery.attempt_count
            >= delivery.max_attempts
        ):
            delivery.attempt_count = 0

        delivery.status = (
            NotificationDeliveryStatus
            .PENDING
            .value
        )

        delivery.next_retry_at = None
        delivery.failed_at = None

        db.add(delivery)
        db.commit()
        db.refresh(delivery)

        return self.execute_delivery(
            db,
            delivery=delivery,
        )

    def list_for_notification(
        self,
        db: Session,
        *,
        notification_id: int,
        skip: int,
        limit: int,
    ) -> AdminNotificationDeliveryListResponse:
        items = (
            admin_notification_delivery_repository
            .list_for_notification(
                db,
                notification_id=notification_id,
                skip=skip,
                limit=limit,
            )
        )

        total = (
            admin_notification_delivery_repository
            .count_for_notification(
                db,
                notification_id=notification_id,
            )
        )

        return AdminNotificationDeliveryListResponse(
            items=[
                self._response(item)
                for item in items
            ],
            total=total,
            skip=skip,
            limit=limit,
        )


admin_notification_delivery_service = (
    AdminNotificationDeliveryService()
)