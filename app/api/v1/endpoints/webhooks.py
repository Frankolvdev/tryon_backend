import json

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.common.exceptions import ForbiddenException
from app.schemas.webhook import IncomingWebhookCreate, IncomingWebhookResponse
from app.services.runtime_settings_service import runtime_settings_service
from app.services.webhook_service import webhook_service

router = APIRouter()


@router.post("/incoming/{provider}", response_model=IncomingWebhookResponse)
async def receive_incoming_webhook(
    provider: str,
    request: Request,
    x_webhook_signature: str | None = Header(default=None, alias="X-Webhook-Signature"),
    db: Session = Depends(get_db),
):
    raw_body = await request.body()

    signing_secret = runtime_settings_service.get_string(
        db,
        f"{provider}_webhook_secret",
        default="",
    )

    if signing_secret:
        is_valid = webhook_service.verify_incoming_signature(
            secret=signing_secret,
            payload_body=raw_body,
            signature_header=x_webhook_signature,
        )

        if not is_valid:
            raise ForbiddenException("Invalid webhook signature.")

    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except json.JSONDecodeError:
        payload = {
            "raw_body": raw_body.decode("utf-8", errors="ignore"),
        }

    event_type = (
        payload.get("type")
        or payload.get("event_type")
        or payload.get("event")
        or f"{provider}.unknown"
    )

    return webhook_service.receive_incoming_webhook(
        db=db,
        data=IncomingWebhookCreate(
            provider=provider,
            event_type=event_type,
            payload=payload,
        ),
    )