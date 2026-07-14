from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.schemas.stripe_billing import StripeWebhookResult
from app.services.billing_event_service import (
    billing_event_service,
)
from app.services.stripe_client_service import (
    stripe_client_service,
)

router = APIRouter()


@router.post(
    "/stripe",
    response_model=StripeWebhookResult,
)
async def receive_stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(
        default=None,
        alias="Stripe-Signature",
    ),
    db: Session = Depends(get_db),
):
    raw_payload = await request.body()

    stripe_event = (
        stripe_client_service.construct_webhook_event(
            db=db,
            payload=raw_payload,
            signature_header=stripe_signature,
        )
    )

    return billing_event_service.receive_and_process(
        db,
        stripe_event=stripe_event,
    )