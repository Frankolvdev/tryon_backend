from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.common.billing_enums import BillingEventStatus


class BillingEventResponse(BaseModel):
    id: int
    provider: str
    provider_event_id: str
    event_type: str
    status: BillingEventStatus

    payload: dict[str, Any]
    result: dict[str, Any]
    error_message: str | None

    processing_attempts: int

    received_at: datetime
    processed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BillingEventListResponse(BaseModel):
    items: list[BillingEventResponse]
    total: int
    skip: int
    limit: int


class BillingEventRetryResponse(BaseModel):
    event: BillingEventResponse
    retried: bool
    message: str