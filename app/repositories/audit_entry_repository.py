from datetime import datetime

from sqlalchemy import (
    func,
    or_,
    select,
)
from sqlalchemy.orm import Session

from app.models.audit_entry import AuditEntry
from app.repositories.base import BaseRepository


class AuditEntryRepository(
    BaseRepository[AuditEntry]
):
    def __init__(self):
        super().__init__(AuditEntry)

    def list_filtered(
        self,
        db: Session,
        *,
        actor_user_id: int | None = None,
        actor_email: str | None = None,
        actor_type: str | None = None,
        action: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        success: bool | None = None,
        correlation_id: str | None = None,
        request_id: str | None = None,
        is_restorable: bool | None = None,
        search: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[AuditEntry]:
        statement = select(AuditEntry)

        statement = self._apply_filters(
            statement,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            actor_type=actor_type,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            success=success,
            correlation_id=correlation_id,
            request_id=request_id,
            is_restorable=is_restorable,
            search=search,
            created_from=created_from,
            created_to=created_to,
        )

        statement = (
            statement
            .order_by(
                AuditEntry.created_at.desc(),
                AuditEntry.id.desc(),
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
        actor_user_id: int | None = None,
        actor_email: str | None = None,
        actor_type: str | None = None,
        action: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        success: bool | None = None,
        correlation_id: str | None = None,
        request_id: str | None = None,
        is_restorable: bool | None = None,
        search: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> int:
        statement = select(
            func.count(AuditEntry.id)
        )

        statement = self._apply_filters(
            statement,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            actor_type=actor_type,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            success=success,
            correlation_id=correlation_id,
            request_id=request_id,
            is_restorable=is_restorable,
            search=search,
            created_from=created_from,
            created_to=created_to,
        )

        return int(
            db.execute(
                statement
            ).scalar_one()
        )

    def list_entity_history(
        self,
        db: Session,
        *,
        entity_type: str,
        entity_id: str,
        limit: int = 500,
    ) -> list[AuditEntry]:
        statement = (
            select(AuditEntry)
            .where(
                AuditEntry.entity_type
                == entity_type,
                AuditEntry.entity_id
                == entity_id,
            )
            .order_by(
                AuditEntry.created_at.desc(),
                AuditEntry.id.desc(),
            )
            .limit(limit)
        )

        return list(
            db.execute(
                statement
            ).scalars().all()
        )

    def count_entity_history(
        self,
        db: Session,
        *,
        entity_type: str,
        entity_id: str,
    ) -> int:
        statement = select(
            func.count(AuditEntry.id)
        ).where(
            AuditEntry.entity_type
            == entity_type,
            AuditEntry.entity_id
            == entity_id,
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
        actor_user_id: int | None,
        actor_email: str | None,
        actor_type: str | None,
        action: str | None,
        entity_type: str | None,
        entity_id: str | None,
        success: bool | None,
        correlation_id: str | None,
        request_id: str | None,
        is_restorable: bool | None,
        search: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
    ):
        if actor_user_id is not None:
            statement = statement.where(
                AuditEntry.actor_user_id
                == actor_user_id
            )

        if actor_email:
            statement = statement.where(
                AuditEntry.actor_email
                == actor_email
            )

        if actor_type:
            statement = statement.where(
                AuditEntry.actor_type
                == actor_type
            )

        if action:
            statement = statement.where(
                AuditEntry.action == action
            )

        if entity_type:
            statement = statement.where(
                AuditEntry.entity_type
                == entity_type
            )

        if entity_id:
            statement = statement.where(
                AuditEntry.entity_id
                == entity_id
            )

        if success is not None:
            statement = statement.where(
                AuditEntry.success.is_(success)
            )

        if correlation_id:
            statement = statement.where(
                AuditEntry.correlation_id
                == correlation_id
            )

        if request_id:
            statement = statement.where(
                AuditEntry.request_id
                == request_id
            )

        if is_restorable is not None:
            statement = statement.where(
                AuditEntry.is_restorable.is_(
                    is_restorable
                )
            )

        if search:
            pattern = f"%{search.strip()}%"

            statement = statement.where(
                or_(
                    AuditEntry.action.ilike(
                        pattern
                    ),
                    AuditEntry.entity_type.ilike(
                        pattern
                    ),
                    AuditEntry.entity_id.ilike(
                        pattern
                    ),
                    AuditEntry.actor_email.ilike(
                        pattern
                    ),
                    AuditEntry.error_message.ilike(
                        pattern
                    ),
                )
            )

        if created_from:
            statement = statement.where(
                AuditEntry.created_at
                >= created_from
            )

        if created_to:
            statement = statement.where(
                AuditEntry.created_at
                < created_to
            )

        return statement


audit_entry_repository = (
    AuditEntryRepository()
)