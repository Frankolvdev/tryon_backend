import hashlib
import hmac
import json
import secrets
import time
from datetime import timedelta
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.common.enums import (
    WebhookDeliveryStatus,
    WebhookEndpointStatus,
    WebhookEventStatus,
)
from app.common.exceptions import ForbiddenException, NotFoundException
from app.common.time import utc_now
from app.models.user import User
from app.models.webhook_delivery import WebhookDelivery
from app.models.webhook_endpoint import WebhookEndpoint
from app.models.webhook_event import WebhookEvent
from app.repositories.webhook_delivery_repository import webhook_delivery_repository
from app.repositories.webhook_endpoint_repository import webhook_endpoint_repository
from app.repositories.webhook_event_repository import webhook_event_repository
from app.schemas.webhook import (
    IncomingWebhookCreate,
    IncomingWebhookResponse,
    WebhookDeliveryResponse,
    WebhookEndpointCreate,
    WebhookEndpointCreateResponse,
    WebhookEndpointResponse,
    WebhookEndpointUpdate,
    WebhookEventCreate,
    WebhookEventResponse,
)


class WebhookService:
    def _serialize_json(self, data: Any) -> str:
        return json.dumps(data, ensure_ascii=False, default=str)

    def _parse_json(self, raw: str | None) -> Any:
        if not raw:
            return None

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    def _generate_secret(self) -> str:
        return f"whsec_{secrets.token_urlsafe(32)}"

    def _parse_list(self, raw: str | None) -> list[str]:
        value = self._parse_json(raw)

        if isinstance(value, list):
            return [str(item) for item in value]

        return []

    def _endpoint_to_response(self, endpoint: WebhookEndpoint) -> WebhookEndpointResponse:
        return WebhookEndpointResponse(
            id=endpoint.id,
            name=endpoint.name,
            url=endpoint.url,
            subscribed_events=self._parse_list(endpoint.subscribed_events_json),
            status=endpoint.status,
            is_active=endpoint.is_active,
            created_by_user_id=endpoint.created_by_user_id,
            description=endpoint.description,
            last_success_at=endpoint.last_success_at,
            last_failure_at=endpoint.last_failure_at,
            created_at=endpoint.created_at,
            updated_at=endpoint.updated_at,
        )

    def _event_to_response(self, event: WebhookEvent) -> WebhookEventResponse:
        return WebhookEventResponse(
            id=event.id,
            event_type=event.event_type,
            source=event.source,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            payload=self._parse_json(event.payload_json) or {},
            status=event.status,
            attempts_count=event.attempts_count,
            max_attempts=event.max_attempts,
            next_attempt_at=event.next_attempt_at,
            delivered_at=event.delivered_at,
            created_at=event.created_at,
            updated_at=event.updated_at,
        )

    def _delivery_to_response(self, delivery: WebhookDelivery) -> WebhookDeliveryResponse:
        return WebhookDeliveryResponse(
            id=delivery.id,
            webhook_event_id=delivery.webhook_event_id,
            webhook_endpoint_id=delivery.webhook_endpoint_id,
            status=delivery.status,
            attempt_number=delivery.attempt_number,
            request_headers=self._parse_json(delivery.request_headers_json),
            request_body=self._parse_json(delivery.request_body_json),
            response_status_code=delivery.response_status_code,
            response_body=delivery.response_body,
            error_message=delivery.error_message,
            duration_ms=delivery.duration_ms,
            created_at=delivery.created_at,
        )

    def _event_matches_endpoint(
        self,
        event_type: str,
        endpoint: WebhookEndpoint,
    ) -> bool:
        subscribed_events = self._parse_list(endpoint.subscribed_events_json)

        if not subscribed_events:
            return True

        return "*" in subscribed_events or event_type in subscribed_events

    def _sign_payload(
        self,
        *,
        secret: str,
        timestamp: int,
        payload_json: str,
    ) -> str:
        signed_payload = f"{timestamp}.{payload_json}".encode("utf-8")
        signature = hmac.new(
            secret.encode("utf-8"),
            signed_payload,
            hashlib.sha256,
        ).hexdigest()

        return f"t={timestamp},v1={signature}"

    def verify_incoming_signature(
        self,
        *,
        secret: str,
        payload_body: bytes,
        signature_header: str | None,
    ) -> bool:
        if not signature_header:
            return False

        expected = hmac.new(
            secret.encode("utf-8"),
            payload_body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature_header)

    def list_endpoints(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[WebhookEndpointResponse]:
        endpoints = webhook_endpoint_repository.list_all(
            db,
            skip=skip,
            limit=limit,
        )
        return [self._endpoint_to_response(endpoint) for endpoint in endpoints]

    def create_endpoint(
        self,
        db: Session,
        *,
        data: WebhookEndpointCreate,
        created_by_user: User,
    ) -> WebhookEndpointCreateResponse:
        secret = self._generate_secret()

        endpoint = webhook_endpoint_repository.create(
            db,
            data={
                "name": data.name,
                "url": str(data.url),
                "secret": secret,
                "subscribed_events_json": self._serialize_json(data.subscribed_events),
                "status": WebhookEndpointStatus.ACTIVE.value,
                "is_active": True,
                "created_by_user_id": created_by_user.id,
                "description": data.description,
            },
        )

        return WebhookEndpointCreateResponse(
            endpoint=self._endpoint_to_response(endpoint),
            signing_secret=secret,
        )

    def update_endpoint(
        self,
        db: Session,
        *,
        endpoint_id: int,
        data: WebhookEndpointUpdate,
    ) -> WebhookEndpointResponse:
        endpoint = webhook_endpoint_repository.get_by_id(db, endpoint_id)

        if not endpoint:
            raise NotFoundException("Webhook endpoint not found.")

        update_data = data.model_dump(exclude_unset=True)
        final_data = {}

        for field in ["name", "description", "is_active"]:
            if field in update_data:
                final_data[field] = update_data[field]

        if "url" in update_data and update_data["url"] is not None:
            final_data["url"] = str(update_data["url"])

        if "status" in update_data and update_data["status"] is not None:
            final_data["status"] = update_data["status"].value

        if "subscribed_events" in update_data:
            final_data["subscribed_events_json"] = self._serialize_json(
                update_data["subscribed_events"]
            )

        updated = webhook_endpoint_repository.update(
            db,
            db_obj=endpoint,
            data=final_data,
        )

        return self._endpoint_to_response(updated)

    def create_event(
        self,
        db: Session,
        *,
        data: WebhookEventCreate,
    ) -> WebhookEventResponse:
        event = webhook_event_repository.create(
            db,
            data={
                "event_type": data.event_type,
                "source": data.source,
                "entity_type": data.entity_type,
                "entity_id": data.entity_id,
                "payload_json": self._serialize_json(data.payload),
                "status": WebhookEventStatus.PENDING.value,
                "attempts_count": 0,
                "max_attempts": data.max_attempts,
                "next_attempt_at": utc_now(),
            },
        )

        return self._event_to_response(event)

    def receive_incoming_webhook(
        self,
        db: Session,
        *,
        data: IncomingWebhookCreate,
    ) -> IncomingWebhookResponse:
        self.create_event(
            db,
            data=WebhookEventCreate(
                event_type=data.event_type,
                source=data.provider,
                entity_type="incoming_webhook",
                entity_id=None,
                payload=data.payload,
                max_attempts=5,
            ),
        )

        return IncomingWebhookResponse(
            received=True,
            provider=data.provider,
            event_type=data.event_type,
        )

    def list_events(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[WebhookEventResponse]:
        events = webhook_event_repository.list_all(db, skip=skip, limit=limit)
        return [self._event_to_response(event) for event in events]

    def list_deliveries_by_event(
        self,
        db: Session,
        *,
        event_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[WebhookDeliveryResponse]:
        deliveries = webhook_delivery_repository.list_by_event_id(
            db,
            event_id,
            skip=skip,
            limit=limit,
        )

        return [self._delivery_to_response(delivery) for delivery in deliveries]

    def deliver_event(
        self,
        db: Session,
        *,
        event_id: int,
        force: bool = False,
    ) -> WebhookEventResponse:
        event = webhook_event_repository.get_by_id(db, event_id)

        if not event:
            raise NotFoundException("Webhook event not found.")

        if event.attempts_count >= event.max_attempts and not force:
            event.status = WebhookEventStatus.FAILED.value
            db.add(event)
            db.commit()
            db.refresh(event)
            return self._event_to_response(event)

        endpoints = webhook_endpoint_repository.list_active(db)

        matched_endpoints = [
            endpoint
            for endpoint in endpoints
            if self._event_matches_endpoint(event.event_type, endpoint)
        ]

        if not matched_endpoints:
            event.status = WebhookEventStatus.DELIVERED.value
            event.delivered_at = utc_now()
            db.add(event)
            db.commit()
            db.refresh(event)
            return self._event_to_response(event)

        event.status = WebhookEventStatus.PROCESSING.value
        event.attempts_count += 1
        db.add(event)
        db.commit()
        db.refresh(event)

        all_success = True

        for endpoint in matched_endpoints:
            success = self._deliver_to_endpoint(
                db=db,
                event=event,
                endpoint=endpoint,
            )

            if not success:
                all_success = False

        if all_success:
            event.status = WebhookEventStatus.DELIVERED.value
            event.delivered_at = utc_now()
            event.next_attempt_at = None
        else:
            if event.attempts_count >= event.max_attempts:
                event.status = WebhookEventStatus.FAILED.value
                event.next_attempt_at = None
            else:
                event.status = WebhookEventStatus.FAILED.value
                delay_minutes = min(60, 2 ** event.attempts_count)
                event.next_attempt_at = utc_now() + timedelta(minutes=delay_minutes)

        db.add(event)
        db.commit()
        db.refresh(event)

        return self._event_to_response(event)

    def process_pending_events(self, db: Session) -> dict:
        pending_events = webhook_event_repository.list_pending_due(
            db,
            now=utc_now(),
            limit=100,
        )

        processed = 0
        skipped = 0

        for event in pending_events:
            if event.attempts_count >= event.max_attempts:
                skipped += 1
                continue

            self.deliver_event(
                db=db,
                event_id=event.id,
                force=False,
            )
            processed += 1

        return {
            "processed": processed,
            "skipped": skipped,
        }

    def _deliver_to_endpoint(
        self,
        *,
        db: Session,
        event: WebhookEvent,
        endpoint: WebhookEndpoint,
    ) -> bool:
        payload = {
            "id": event.id,
            "type": event.event_type,
            "source": event.source,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "created_at": event.created_at.isoformat(),
            "data": self._parse_json(event.payload_json) or {},
        }

        payload_json = self._serialize_json(payload)
        timestamp = int(time.time())
        signature = self._sign_payload(
            secret=endpoint.secret,
            timestamp=timestamp,
            payload_json=payload_json,
        )

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AI-TryOn-Webhooks/1.0",
            "X-Webhook-Event": event.event_type,
            "X-Webhook-Signature": signature,
        }

        started = time.perf_counter()

        response_status_code = None
        response_body = None
        error_message = None
        success = False

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    endpoint.url,
                    content=payload_json,
                    headers=headers,
                )

            response_status_code = response.status_code
            response_body = response.text[:5000]
            success = 200 <= response.status_code < 300

        except Exception as error:
            error_message = str(error)
            success = False

        duration_ms = int((time.perf_counter() - started) * 1000)

        delivery = WebhookDelivery(
            webhook_event_id=event.id,
            webhook_endpoint_id=endpoint.id,
            status=(
                WebhookDeliveryStatus.SUCCESS.value
                if success
                else WebhookDeliveryStatus.FAILED.value
            ),
            attempt_number=event.attempts_count,
            request_headers_json=self._serialize_json(headers),
            request_body_json=payload_json,
            response_status_code=response_status_code,
            response_body=response_body,
            error_message=error_message,
            duration_ms=duration_ms,
        )

        if success:
            endpoint.last_success_at = utc_now()
        else:
            endpoint.last_failure_at = utc_now()

        db.add(delivery)
        db.add(endpoint)
        db.commit()

        return success


webhook_service = WebhookService()