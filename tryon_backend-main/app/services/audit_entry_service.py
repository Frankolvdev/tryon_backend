import logging
from datetime import datetime
from typing import Any

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit_enums import (
    AuditActorType,
)
from app.common.exceptions import (
    NotFoundException,
)
from app.common.time import utc_now
from app.models.audit_entry import AuditEntry
from app.models.user import User
from app.observability.context import (
    get_correlation_id,
)
from app.repositories.audit_entry_repository import (
    audit_entry_repository,
)
from app.schemas.audit_entry import (
    AuditDiffResponse,
    AuditEntityHistoryResponse,
    AuditEntryCreate,
    AuditEntryListResponse,
    AuditEntryResponse,
    AuditSummaryResponse,
)
from app.services.audit_diff_service import (
    audit_diff_service,
)
from app.services.audit_snapshot_service import (
    audit_snapshot_service,
)


logger = logging.getLogger(
    "app.audit_entries"
)


class AuditEntryService:
    def _response(
        self,
        entry: AuditEntry,
    ) -> AuditEntryResponse:
        return AuditEntryResponse(
            id=entry.id,
            actor_user_id=entry.actor_user_id,
            actor_email=entry.actor_email,
            actor_type=entry.actor_type,
            action=entry.action,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            success=entry.success,
            before_data=entry.before_data,
            after_data=entry.after_data,
            diff_data=entry.diff_data,
            metadata=entry.metadata_json or {},
            ip_address=entry.ip_address,
            user_agent=entry.user_agent,
            correlation_id=entry.correlation_id,
            request_id=entry.request_id,
            error_type=entry.error_type,
            error_message=entry.error_message,
            is_restorable=entry.is_restorable,
            restored_from_entry_id=(
                entry.restored_from_entry_id
            ),
            created_at=entry.created_at,
        )

    def _request_ip(
        self,
        request: Request | None,
    ) -> str | None:
        if request is None:
            return None

        forwarded_for = request.headers.get(
            "x-forwarded-for"
        )

        if forwarded_for:
            return (
                forwarded_for
                .split(",")[0]
                .strip()
            )

        if request.client:
            return request.client.host

        return None

    def _request_id(
        self,
        request: Request | None,
    ) -> str | None:
        if request is None:
            return None

        return (
            request.headers.get("x-request-id")
            or request.headers.get(
                "x-correlation-id"
            )
        )

    def _resolve_actor_type(
        self,
        actor: User | None,
        requested_actor_type: str | None,
    ) -> str:
        if requested_actor_type:
            return requested_actor_type

        if actor is None:
            return AuditActorType.SYSTEM.value

        if bool(
            getattr(
                actor,
                "is_admin",
                False,
            )
        ):
            return AuditActorType.ADMIN.value

        return AuditActorType.USER.value

    def create(
        self,
        db: Session,
        *,
        data: AuditEntryCreate,
        commit: bool = True,
    ) -> AuditEntryResponse:
        before_snapshot = (
            audit_snapshot_service.snapshot(
                data.before_data
            )
        )

        after_snapshot = (
            audit_snapshot_service.snapshot(
                data.after_data
            )
        )

        diff_data = (
            audit_diff_service.as_dict(
                before_data=before_snapshot,
                after_data=after_snapshot,
            )
        )

        entity_id = (
            str(data.entity_id)
            if data.entity_id is not None
            else None
        )

        entry = AuditEntry(
            actor_user_id=data.actor_user_id,
            actor_email=data.actor_email,
            actor_type=data.actor_type,
            action=data.action,
            entity_type=data.entity_type,
            entity_id=entity_id,
            success=data.success,
            before_data=before_snapshot,
            after_data=after_snapshot,
            diff_data=diff_data,
            metadata_json=(
                audit_snapshot_service.snapshot(
                    data.metadata
                )
                or {}
            ),
            ip_address=data.ip_address,
            user_agent=data.user_agent,
            correlation_id=(
                data.correlation_id
                or get_correlation_id()
            ),
            request_id=data.request_id,
            error_type=data.error_type,
            error_message=data.error_message,
            is_restorable=(
                data.is_restorable
                and before_snapshot is not None
            ),
            restored_from_entry_id=(
                data.restored_from_entry_id
            ),
        )

        db.add(entry)

        if commit:
            db.commit()
            db.refresh(entry)
        else:
            db.flush()

        logger.info(
            "Advanced audit entry created.",
            extra={
                "audit_entry_id": entry.id,
                "actor_user_id": (
                    entry.actor_user_id
                ),
                "actor_type": entry.actor_type,
                "action": entry.action,
                "entity_type": entry.entity_type,
                "entity_id": entry.entity_id,
                "success": entry.success,
                "is_restorable": (
                    entry.is_restorable
                ),
            },
        )

        return self._response(entry)

    def record(
        self,
        db: Session,
        *,
        action: str,
        entity_type: str,
        entity_id: str | int | None = None,
        actor: User | None = None,
        actor_type: str | None = None,
        actor_email: str | None = None,
        before: Any = None,
        after: Any = None,
        metadata: dict[str, Any] | None = None,
        request: Request | None = None,
        success: bool = True,
        exception: Exception | None = None,
        is_restorable: bool = False,
        restored_from_entry_id: int | None = None,
        commit: bool = True,
    ) -> AuditEntryResponse:
        resolved_email = (
            actor_email
            or (
                getattr(
                    actor,
                    "email",
                    None,
                )
                if actor is not None
                else None
            )
        )

        return self.create(
            db,
            data=AuditEntryCreate(
                actor_user_id=(
                    getattr(
                        actor,
                        "id",
                        None,
                    )
                    if actor is not None
                    else None
                ),
                actor_email=resolved_email,
                actor_type=(
                    self._resolve_actor_type(
                        actor,
                        actor_type,
                    )
                ),
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                success=success,
                before_data=(
                    audit_snapshot_service
                    .snapshot(before)
                ),
                after_data=(
                    audit_snapshot_service
                    .snapshot(after)
                ),
                metadata=metadata or {},
                ip_address=self._request_ip(
                    request
                ),
                user_agent=(
                    request.headers.get(
                        "user-agent"
                    )
                    if request is not None
                    else None
                ),
                correlation_id=(
                    get_correlation_id()
                ),
                request_id=self._request_id(
                    request
                ),
                error_type=(
                    exception.__class__.__name__
                    if exception is not None
                    else None
                ),
                error_message=(
                    str(exception)
                    if exception is not None
                    else None
                ),
                is_restorable=is_restorable,
                restored_from_entry_id=(
                    restored_from_entry_id
                ),
            ),
            commit=commit,
        )

    def safe_record(
        self,
        db: Session,
        *,
        action: str,
        entity_type: str,
        entity_id: str | int | None = None,
        actor: User | None = None,
        actor_type: str | None = None,
        actor_email: str | None = None,
        before: Any = None,
        after: Any = None,
        metadata: dict[str, Any] | None = None,
        request: Request | None = None,
        success: bool = True,
        exception: Exception | None = None,
        is_restorable: bool = False,
        restored_from_entry_id: int | None = None,
    ) -> AuditEntryResponse | None:
        try:
            return self.record(
                db,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                actor=actor,
                actor_type=actor_type,
                actor_email=actor_email,
                before=before,
                after=after,
                metadata=metadata,
                request=request,
                success=success,
                exception=exception,
                is_restorable=is_restorable,
                restored_from_entry_id=(
                    restored_from_entry_id
                ),
            )

        except Exception:
            db.rollback()

            logger.exception(
                "Could not persist advanced audit entry.",
                extra={
                    "action": action,
                    "entity_type": entity_type,
                    "entity_id": (
                        str(entity_id)
                        if entity_id is not None
                        else None
                    ),
                },
            )

            return None

    def get(
        self,
        db: Session,
        *,
        entry_id: int,
    ) -> AuditEntry:
        entry = (
            audit_entry_repository.get_by_id(
                db,
                entry_id,
            )
        )

        if not entry:
            raise NotFoundException(
                "Audit entry not found."
            )

        return entry

    def get_response(
        self,
        db: Session,
        *,
        entry_id: int,
    ) -> AuditEntryResponse:
        return self._response(
            self.get(
                db,
                entry_id=entry_id,
            )
        )

    def get_diff(
        self,
        db: Session,
        *,
        entry_id: int,
    ) -> AuditDiffResponse:
        entry = self.get(
            db,
            entry_id=entry_id,
        )

        return audit_diff_service.compare(
            before_data=entry.before_data,
            after_data=entry.after_data,
        )

    def list_entries(
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
    ) -> AuditEntryListResponse:
        items = (
            audit_entry_repository
            .list_filtered(
                db,
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
                skip=skip,
                limit=limit,
            )
        )

        total = (
            audit_entry_repository
            .count_filtered(
                db,
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
        )

        return AuditEntryListResponse(
            items=[
                self._response(item)
                for item in items
            ],
            total=total,
            skip=skip,
            limit=limit,
        )

    def entity_history(
        self,
        db: Session,
        *,
        entity_type: str,
        entity_id: str,
        limit: int = 500,
    ) -> AuditEntityHistoryResponse:
        items = (
            audit_entry_repository
            .list_entity_history(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
                limit=limit,
            )
        )

        total = (
            audit_entry_repository
            .count_entity_history(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
            )
        )

        return AuditEntityHistoryResponse(
            entity_type=entity_type,
            entity_id=entity_id,
            items=[
                self._response(item)
                for item in items
            ],
            total=total,
        )

    def summary(
        self,
        db: Session,
    ) -> AuditSummaryResponse:
        total_entries = int(
            db.execute(
                select(
                    func.count(AuditEntry.id)
                )
            ).scalar_one()
        )

        successful_entries = int(
            db.execute(
                select(
                    func.count(AuditEntry.id)
                ).where(
                    AuditEntry.success.is_(True)
                )
            ).scalar_one()
        )

        failed_entries = int(
            db.execute(
                select(
                    func.count(AuditEntry.id)
                ).where(
                    AuditEntry.success.is_(False)
                )
            ).scalar_one()
        )

        restorable_entries = int(
            db.execute(
                select(
                    func.count(AuditEntry.id)
                ).where(
                    AuditEntry.is_restorable.is_(
                        True
                    )
                )
            ).scalar_one()
        )

        actor_rows = db.execute(
            select(
                AuditEntry.actor_type,
                func.count(AuditEntry.id),
            )
            .group_by(
                AuditEntry.actor_type
            )
        ).all()

        action_rows = db.execute(
            select(
                AuditEntry.action,
                func.count(AuditEntry.id),
            )
            .group_by(
                AuditEntry.action
            )
        ).all()

        entity_rows = db.execute(
            select(
                AuditEntry.entity_type,
                func.count(AuditEntry.id),
            )
            .group_by(
                AuditEntry.entity_type
            )
        ).all()

        return AuditSummaryResponse(
            total_entries=total_entries,
            successful_entries=(
                successful_entries
            ),
            failed_entries=failed_entries,
            restorable_entries=(
                restorable_entries
            ),
            by_actor_type={
                str(actor_type): int(total)
                for actor_type, total
                in actor_rows
            },
            by_action={
                str(action): int(total)
                for action, total
                in action_rows
            },
            by_entity_type={
                str(entity_type): int(total)
                for entity_type, total
                in entity_rows
            },
            generated_at=utc_now(),
        )


audit_entry_service = AuditEntryService()