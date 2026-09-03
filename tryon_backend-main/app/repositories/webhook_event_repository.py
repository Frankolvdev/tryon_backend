from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import WebhookEventStatus
from app.models.webhook_event import WebhookEvent
from app.repositories.base import BaseRepository


class WebhookEventRepository(BaseRepository[WebhookEvent]):
    def __init__(self):
        super().__init__(WebhookEvent)

    def list_all(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[WebhookEvent]:
        statement = (
            select(WebhookEvent)
            .order_by(WebhookEvent.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())

    def list_pending_due(
        self,
        db: Session,
        *,
        now: datetime,
        limit: int = 100,
    ) -> list[WebhookEvent]:
        statement = (
            select(WebhookEvent)
            .where(WebhookEvent.status.in_([
                WebhookEventStatus.PENDING.value,
                WebhookEventStatus.FAILED.value,
            ]))
            .where(
                (WebhookEvent.next_attempt_at.is_(None))
                | (WebhookEvent.next_attempt_at <= now)
            )
            .where(WebhookEvent.attempts_count < WebhookEvent.max_attempts)
            .order_by(WebhookEvent.created_at.asc())
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())


webhook_event_repository = WebhookEventRepository()