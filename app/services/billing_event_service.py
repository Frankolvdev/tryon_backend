import json
from typing import Any

from sqlalchemy.orm import Session

from app.common.billing_enums import (
    BillingEventStatus,
    BillingProvider,
)
from app.common.time import utc_now
from app.models.billing_event import BillingEvent
from app.repositories.billing_event_repository import (
    billing_event_repository,
)
from app.schemas.billing_event import (
    BillingEventListResponse,
    BillingEventResponse,
    BillingEventRetryResponse,
)
from app.schemas.stripe_billing import StripeWebhookResult


class BillingEventService:
    def _serialize(self, value: Any) -> str:
        return json.dumps(
            value or {},
            ensure_ascii=False,
            default=str,
        )

    def _stripe_event_to_dict(
        self,
        stripe_event: Any,
    ) -> dict:
        if isinstance(stripe_event, dict):
            return stripe_event

        to_dict_recursive = getattr(
            stripe_event,
            "to_dict_recursive",
            None,
        )

        if callable(to_dict_recursive):
            parsed = to_dict_recursive()

            if isinstance(parsed, dict):
                return parsed

        to_dict = getattr(
            stripe_event,
            "to_dict",
            None,
        )

        if callable(to_dict):
            parsed = to_dict()

            if isinstance(parsed, dict):
                return parsed

        raise TypeError(
            "Stripe event could not be converted to a dictionary."
        )

    def _parse(self, value: str | None) -> dict:
        if not value:
            return {}

        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _response(
        self,
        event: BillingEvent,
    ) -> BillingEventResponse:
        return BillingEventResponse(
            id=event.id,
            provider=event.provider,
            provider_event_id=event.provider_event_id,
            event_type=event.event_type,
            status=event.status,
            payload=self._parse(event.payload_json),
            result=self._parse(event.result_json),
            error_message=event.error_message,
            processing_attempts=event.processing_attempts,
            received_at=event.received_at,
            processed_at=event.processed_at,
            created_at=event.created_at,
            updated_at=event.updated_at,
        )

    def list_events(
        self,
        db: Session,
        *,
        event_type: str | None = None,
        status: BillingEventStatus | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> BillingEventListResponse:
        status_value = status.value if status else None

        events = billing_event_repository.list_all_filtered(
            db,
            event_type=event_type,
            status=status_value,
            skip=skip,
            limit=limit,
        )

        total = billing_event_repository.count_filtered(
            db,
            event_type=event_type,
            status=status_value,
        )

        return BillingEventListResponse(
            items=[
                self._response(event)
                for event in events
            ],
            total=total,
            skip=skip,
            limit=limit,
        )

    def receive_and_process(
        self,
        db: Session,
        *,
        stripe_event: Any,
    ) -> StripeWebhookResult:
        event_id = stripe_event["id"]
        event_type = stripe_event["type"]

        event, created = (
            billing_event_repository.create_if_missing(
                db,
                data={
                    "provider": BillingProvider.STRIPE.value,
                    "provider_event_id": event_id,
                    "event_type": event_type,
                    "status": BillingEventStatus.RECEIVED.value,
                    "payload_json": self._serialize(
                        self._stripe_event_to_dict(
                            stripe_event,
                        )
                    ),
                    "processing_attempts": 0,
                    "received_at": utc_now(),
                },
            )
        )

        if (
            not created
            and event.status
            == BillingEventStatus.PROCESSED.value
        ):
            return StripeWebhookResult(
                received=True,
                event_type=event_type,
                message=(
                    "Stripe event was already processed. "
                    "No duplicate business action was executed."
                ),
                metadata={
                    "stripe_event_id": event_id,
                    "duplicate": True,
                    "billing_event_id": event.id,
                },
            )

        return self._process_stored_event(
            db,
            event=event,
            stripe_event=stripe_event,
        )

    def _process_stored_event(
        self,
        db: Session,
        *,
        event: BillingEvent,
        stripe_event: Any,
    ) -> StripeWebhookResult:
        event = billing_event_repository.get_for_update(
            db,
            event_id=event.id,
        )

        if (
            event.status
            == BillingEventStatus.PROCESSED.value
        ):
            return StripeWebhookResult(
                received=True,
                event_type=event.event_type,
                message="Stripe event was already processed.",
                metadata={
                    "stripe_event_id": event.provider_event_id,
                    "duplicate": True,
                    "billing_event_id": event.id,
                },
            )

        event.status = BillingEventStatus.PROCESSING.value
        event.processing_attempts += 1
        event.error_message = None

        db.add(event)
        db.commit()
        db.refresh(event)

        try:
            from app.services.billing_service import billing_service

            result = billing_service.handle_verified_stripe_event(
                db,
                event=stripe_event,
            )

            event.status = BillingEventStatus.PROCESSED.value
            event.result_json = self._serialize(
                result.model_dump(mode="json")
            )
            event.error_message = None
            event.processed_at = utc_now()

            db.add(event)
            db.commit()
            db.refresh(event)

            result.metadata["billing_event_id"] = event.id
            result.metadata["duplicate"] = False

            return result

        except Exception as error:
            event.status = BillingEventStatus.FAILED.value
            event.error_message = str(error)

            db.add(event)
            db.commit()
            db.refresh(event)

            raise

    def retry_event(
        self,
        db: Session,
        *,
        event_id: int,
    ) -> BillingEventRetryResponse:
        event = billing_event_repository.get_by_id(
            db,
            event_id,
        )

        if not event:
            from app.common.exceptions import NotFoundException

            raise NotFoundException(
                "Billing event not found."
            )

        if event.status == BillingEventStatus.PROCESSED.value:
            return BillingEventRetryResponse(
                event=self._response(event),
                retried=False,
                message="Billing event was already processed.",
            )

        stripe_event = self._parse(event.payload_json)

        self._process_stored_event(
            db,
            event=event,
            stripe_event=stripe_event,
        )

        updated = billing_event_repository.get_by_id(
            db,
            event.id,
        )

        return BillingEventRetryResponse(
            event=self._response(updated),
            retried=True,
            message="Billing event retried successfully.",
        )


billing_event_service = BillingEventService()