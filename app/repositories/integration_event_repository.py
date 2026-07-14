from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integration_event import IntegrationEvent
from app.repositories.base import BaseRepository


class IntegrationEventRepository(BaseRepository[IntegrationEvent]):
    def __init__(self):
        super().__init__(IntegrationEvent)

    def list_all(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[IntegrationEvent]:
        statement = (
            select(IntegrationEvent)
            .order_by(IntegrationEvent.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(db.execute(statement).scalars().all())

    def list_by_provider(
        self,
        db: Session,
        provider: str,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[IntegrationEvent]:
        statement = (
            select(IntegrationEvent)
            .where(IntegrationEvent.provider == provider)
            .order_by(IntegrationEvent.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(db.execute(statement).scalars().all())


integration_event_repository = IntegrationEventRepository()