from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import WebhookEndpointStatus
from app.models.webhook_endpoint import WebhookEndpoint
from app.repositories.base import BaseRepository


class WebhookEndpointRepository(BaseRepository[WebhookEndpoint]):
    def __init__(self):
        super().__init__(WebhookEndpoint)

    def list_all(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[WebhookEndpoint]:
        statement = (
            select(WebhookEndpoint)
            .order_by(WebhookEndpoint.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())

    def list_active(self, db: Session) -> list[WebhookEndpoint]:
        statement = (
            select(WebhookEndpoint)
            .where(WebhookEndpoint.is_active.is_(True))
            .where(WebhookEndpoint.status == WebhookEndpointStatus.ACTIVE.value)
            .order_by(WebhookEndpoint.created_at.desc())
        )

        return list(db.execute(statement).scalars().all())


webhook_endpoint_repository = WebhookEndpointRepository()