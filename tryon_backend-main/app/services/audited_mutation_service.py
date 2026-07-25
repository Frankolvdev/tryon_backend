from collections.abc import Callable
from typing import Any, TypeVar

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.audit_entry import (
    AuditEntryResponse,
)
from app.services.audit_entry_service import (
    audit_entry_service,
)
from app.services.audit_snapshot_service import (
    audit_snapshot_service,
)


T = TypeVar("T")


class AuditedMutationService:
    def execute(
        self,
        db: Session,
        *,
        action: str,
        entity_type: str,
        entity_id: str | int | None,
        actor: User | None,
        request: Request | None,
        before: Any,
        operation: Callable[[], T],
        after_loader: Callable[[T], Any] | None = None,
        metadata: dict[str, Any] | None = None,
        is_restorable: bool = False,
        commit: bool = True,
    ) -> tuple[
        T,
        AuditEntryResponse,
    ]:
        before_snapshot = (
            audit_snapshot_service.snapshot(
                before
            )
        )

        try:
            result = operation()

            after_value = (
                after_loader(result)
                if after_loader
                else result
            )

            after_snapshot = (
                audit_snapshot_service.snapshot(
                    after_value
                )
            )

            audit_entry = (
                audit_entry_service.record(
                    db,
                    action=action,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    actor=actor,
                    before=before_snapshot,
                    after=after_snapshot,
                    request=request,
                    metadata=metadata or {},
                    is_restorable=(
                        is_restorable
                    ),
                    commit=False,
                )
            )

            if commit:
                db.commit()

            return result, audit_entry

        except Exception as error:
            db.rollback()

            audit_entry_service.safe_record(
                db,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                actor=actor,
                before=before_snapshot,
                after=None,
                request=request,
                success=False,
                exception=error,
                metadata=metadata or {},
            )

            raise

    def record_created(
        self,
        db: Session,
        *,
        entity_type: str,
        entity: Any,
        actor: User | None,
        request: Request | None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEntryResponse:
        entity_id = getattr(
            entity,
            "id",
            None,
        )

        return audit_entry_service.record(
            db,
            action="create",
            entity_type=entity_type,
            entity_id=entity_id,
            actor=actor,
            before=None,
            after=entity,
            request=request,
            metadata=metadata or {},
            is_restorable=False,
        )

    def record_updated(
        self,
        db: Session,
        *,
        entity_type: str,
        entity: Any,
        before: Any,
        actor: User | None,
        request: Request | None,
        metadata: dict[str, Any] | None = None,
        is_restorable: bool = True,
    ) -> AuditEntryResponse:
        entity_id = getattr(
            entity,
            "id",
            None,
        )

        return audit_entry_service.record(
            db,
            action="update",
            entity_type=entity_type,
            entity_id=entity_id,
            actor=actor,
            before=before,
            after=entity,
            request=request,
            metadata=metadata or {},
            is_restorable=is_restorable,
        )

    def record_deleted(
        self,
        db: Session,
        *,
        entity_type: str,
        entity_id: str | int,
        before: Any,
        actor: User | None,
        request: Request | None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEntryResponse:
        return audit_entry_service.record(
            db,
            action="delete",
            entity_type=entity_type,
            entity_id=entity_id,
            actor=actor,
            before=before,
            after=None,
            request=request,
            metadata=metadata or {},
            is_restorable=False,
        )


audited_mutation_service = (
    AuditedMutationService()
)