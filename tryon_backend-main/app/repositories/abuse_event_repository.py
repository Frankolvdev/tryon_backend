from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.abuse_event import AbuseEvent
from app.repositories.base import BaseRepository


class AbuseEventRepository(BaseRepository[AbuseEvent]):
    def __init__(self):
        super().__init__(AbuseEvent)

    def list_filtered(
        self,
        db: Session,
        *,
        event_type: str | None = None,
        severity: str | None = None,
        status: str | None = None,
        user_id: int | None = None,
        ip_address: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[AbuseEvent]:
        statement = select(AbuseEvent)

        if event_type is not None:
            statement = statement.where(
                AbuseEvent.event_type == event_type,
            )

        if severity is not None:
            statement = statement.where(
                AbuseEvent.severity == severity,
            )

        if status is not None:
            statement = statement.where(
                AbuseEvent.status == status,
            )

        if user_id is not None:
            statement = statement.where(
                AbuseEvent.user_id == user_id,
            )

        if ip_address is not None:
            statement = statement.where(
                AbuseEvent.ip_address == ip_address,
            )

        statement = (
            statement
            .order_by(
                AbuseEvent.created_at.desc(),
                AbuseEvent.id.desc(),
            )
            .offset(skip)
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())

    def count_filtered(
        self,
        db: Session,
        *,
        event_type: str | None = None,
        severity: str | None = None,
        status: str | None = None,
        user_id: int | None = None,
        ip_address: str | None = None,
    ) -> int:
        statement = select(func.count(AbuseEvent.id))

        if event_type is not None:
            statement = statement.where(
                AbuseEvent.event_type == event_type,
            )

        if severity is not None:
            statement = statement.where(
                AbuseEvent.severity == severity,
            )

        if status is not None:
            statement = statement.where(
                AbuseEvent.status == status,
            )

        if user_id is not None:
            statement = statement.where(
                AbuseEvent.user_id == user_id,
            )

        if ip_address is not None:
            statement = statement.where(
                AbuseEvent.ip_address == ip_address,
            )

        return int(db.execute(statement).scalar_one())


abuse_event_repository = AbuseEventRepository()