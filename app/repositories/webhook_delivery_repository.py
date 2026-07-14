from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.webhook_delivery import WebhookDelivery
from app.repositories.base import BaseRepository


class WebhookDeliveryRepository(BaseRepository[WebhookDelivery]):
    def __init__(self):
        super().__init__(WebhookDelivery)

    def list_by_event_id(
        self,
        db: Session,
        webhook_event_id: int,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[WebhookDelivery]:
        statement = (
            select(WebhookDelivery)
            .where(WebhookDelivery.webhook_event_id == webhook_event_id)
            .order_by(WebhookDelivery.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())

    def list_by_endpoint_id(
        self,
        db: Session,
        webhook_endpoint_id: int,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[WebhookDelivery]:
        statement = (
            select(WebhookDelivery)
            .where(WebhookDelivery.webhook_endpoint_id == webhook_endpoint_id)
            .order_by(WebhookDelivery.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())


webhook_delivery_repository = WebhookDeliveryRepository()