from datetime import datetime

from sqlalchemy import (
    func,
    or_,
    select,
)
from sqlalchemy.orm import Session

from app.models.operational_event import (
    OperationalEvent,
)
from app.repositories.base import BaseRepository


class OperationalEventRepository(
    BaseRepository[OperationalEvent]
):
    def __init__(self):
        super().__init__(OperationalEvent)

    def list_filtered(
        self,
        db: Session,
        *,
        source: str | None = None,
        severity: str | None = None,
        event_type: str | None = None,
        is_resolved: bool | None = None,
        correlation_id: str | None = None,
        user_id: int | None = None,
        background_job_id: int | None = None,
        tryon_job_id: int | None = None,
        search: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[OperationalEvent]:
        statement = select(
            OperationalEvent
        )

        statement = self._apply_filters(
            statement,
            source=source,
            severity=severity,
            event_type=event_type,
            is_resolved=is_resolved,
            correlation_id=correlation_id,
            user_id=user_id,
            background_job_id=background_job_id,
            tryon_job_id=tryon_job_id,
            search=search,
            created_from=created_from,
            created_to=created_to,
        )

        statement = (
            statement
            .order_by(
                OperationalEvent.created_at.desc(),
                OperationalEvent.id.desc(),
            )
            .offset(skip)
            .limit(limit)
        )

        return list(
            db.execute(
                statement
            ).scalars().all()
        )

    def count_filtered(
        self,
        db: Session,
        *,
        source: str | None = None,
        severity: str | None = None,
        event_type: str | None = None,
        is_resolved: bool | None = None,
        correlation_id: str | None = None,
        user_id: int | None = None,
        background_job_id: int | None = None,
        tryon_job_id: int | None = None,
        search: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> int:
        statement = select(
            func.count(
                OperationalEvent.id
            )
        )

        statement = self._apply_filters(
            statement,
            source=source,
            severity=severity,
            event_type=event_type,
            is_resolved=is_resolved,
            correlation_id=correlation_id,
            user_id=user_id,
            background_job_id=background_job_id,
            tryon_job_id=tryon_job_id,
            search=search,
            created_from=created_from,
            created_to=created_to,
        )

        return int(
            db.execute(
                statement
            ).scalar_one()
        )

    def _apply_filters(
        self,
        statement,
        *,
        source: str | None,
        severity: str | None,
        event_type: str | None,
        is_resolved: bool | None,
        correlation_id: str | None,
        user_id: int | None,
        background_job_id: int | None,
        tryon_job_id: int | None,
        search: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
    ):
        if source:
            statement = statement.where(
                OperationalEvent.source == source
            )

        if severity:
            statement = statement.where(
                OperationalEvent.severity == severity
            )

        if event_type:
            statement = statement.where(
                OperationalEvent.event_type
                == event_type
            )

        if is_resolved is not None:
            statement = statement.where(
                OperationalEvent.is_resolved.is_(
                    is_resolved
                )
            )

        if correlation_id:
            statement = statement.where(
                OperationalEvent.correlation_id
                == correlation_id
            )

        if user_id is not None:
            statement = statement.where(
                OperationalEvent.user_id == user_id
            )

        if background_job_id is not None:
            statement = statement.where(
                OperationalEvent.background_job_id
                == background_job_id
            )

        if tryon_job_id is not None:
            statement = statement.where(
                OperationalEvent.tryon_job_id
                == tryon_job_id
            )

        if search:
            pattern = f"%{search.strip()}%"

            statement = statement.where(
                or_(
                    OperationalEvent.message.ilike(
                        pattern
                    ),
                    OperationalEvent.exception_message.ilike(
                        pattern
                    ),
                    OperationalEvent.provider_job_id.ilike(
                        pattern
                    ),
                )
            )

        if created_from:
            statement = statement.where(
                OperationalEvent.created_at
                >= created_from
            )

        if created_to:
            statement = statement.where(
                OperationalEvent.created_at
                < created_to
            )

        return statement


operational_event_repository = (
    OperationalEventRepository()
)