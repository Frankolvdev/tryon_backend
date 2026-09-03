import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.exceptions import (
    NotFoundException,
)
from app.common.time import utc_now
from app.models.operational_event import (
    OperationalEvent,
)
from app.observability.business_metrics import (
    OPERATIONAL_EVENTS_TOTAL,
    OPERATIONAL_EVENTS_UNRESOLVED,
)
from app.observability.context import (
    get_correlation_id,
)
from app.repositories.operational_event_repository import (
    operational_event_repository,
)
from app.schemas.operational_event import (
    OperationalEventCreate,
    OperationalEventListResponse,
    OperationalEventResponse,
    OperationalEventSummaryResponse,
)


logger = logging.getLogger(
    "app.operational_events"
)


class OperationalEventService:
    def _serialize_details(
        self,
        details: dict[str, Any],
    ) -> str:
        return json.dumps(
            details,
            ensure_ascii=False,
            default=str,
        )

    def _parse_details(
        self,
        value: str | None,
    ) -> dict[str, Any]:
        if not value:
            return {}

        try:
            parsed = json.loads(value)

            if isinstance(parsed, dict):
                return parsed

        except (
            TypeError,
            json.JSONDecodeError,
        ):
            pass

        return {}

    def _response(
        self,
        event: OperationalEvent,
    ) -> OperationalEventResponse:
        return OperationalEventResponse(
            id=event.id,
            event_type=event.event_type,
            source=event.source,
            severity=event.severity,
            message=event.message,
            correlation_id=event.correlation_id,
            user_id=event.user_id,
            background_job_id=(
                event.background_job_id
            ),
            tryon_job_id=event.tryon_job_id,
            provider_job_id=(
                event.provider_job_id
            ),
            exception_type=event.exception_type,
            exception_message=(
                event.exception_message
            ),
            details=self._parse_details(
                event.details_json
            ),
            is_resolved=event.is_resolved,
            resolved_by_user_id=(
                event.resolved_by_user_id
            ),
            resolved_at=event.resolved_at,
            resolution_note=event.resolution_note,
            created_at=event.created_at,
        )

    def create(
        self,
        db: Session,
        *,
        data: OperationalEventCreate,
        commit: bool = True,
    ) -> OperationalEventResponse:
        event = OperationalEvent(
            event_type=data.event_type,
            source=data.source,
            severity=data.severity,
            message=data.message,
            correlation_id=(
                data.correlation_id
                or get_correlation_id()
            ),
            user_id=data.user_id,
            background_job_id=(
                data.background_job_id
            ),
            tryon_job_id=data.tryon_job_id,
            provider_job_id=(
                data.provider_job_id
            ),
            exception_type=data.exception_type,
            exception_message=(
                data.exception_message
            ),
            details_json=self._serialize_details(
                data.details
            ),
        )

        db.add(event)

        if commit:
            db.commit()
            db.refresh(event)
        else:
            db.flush()

        OPERATIONAL_EVENTS_TOTAL.labels(
            source=data.source,
            event_type=data.event_type,
            severity=data.severity,
        ).inc()

        logger.log(
            self._logging_level(
                data.severity
            ),
            data.message,
            extra={
                "event_type": data.event_type,
                "source": data.source,
                "severity": data.severity,
                "background_job_id": (
                    data.background_job_id
                ),
                "tryon_job_id": (
                    data.tryon_job_id
                ),
                "provider_job_id": (
                    data.provider_job_id
                ),
                "exception_type": (
                    data.exception_type
                ),
            },
        )

        return self._response(event)

    def safe_create(
        self,
        db: Session,
        *,
        event_type: str,
        source: str,
        severity: str,
        message: str,
        user_id: int | None = None,
        background_job_id: int | None = None,
        tryon_job_id: int | None = None,
        provider_job_id: str | None = None,
        exception: Exception | None = None,
        details: dict[str, Any] | None = None,
    ) -> OperationalEventResponse | None:
        try:
            return self.create(
                db,
                data=OperationalEventCreate(
                    event_type=event_type,
                    source=source,
                    severity=severity,
                    message=message,
                    user_id=user_id,
                    background_job_id=(
                        background_job_id
                    ),
                    tryon_job_id=tryon_job_id,
                    provider_job_id=(
                        provider_job_id
                    ),
                    exception_type=(
                        exception.__class__.__name__
                        if exception
                        else None
                    ),
                    exception_message=(
                        str(exception)
                        if exception
                        else None
                    ),
                    details=details or {},
                ),
            )

        except Exception:
            db.rollback()

            logger.exception(
                "Could not persist operational event.",
                extra={
                    "original_event_type": event_type,
                    "original_source": source,
                    "original_severity": severity,
                },
            )

            return None

    def _logging_level(
        self,
        severity: str,
    ) -> int:
        mapping = {
            "info": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR,
            "critical": logging.CRITICAL,
        }

        return mapping.get(
            severity,
            logging.INFO,
        )

    def get(
        self,
        db: Session,
        *,
        event_id: int,
    ) -> OperationalEvent:
        event = (
            operational_event_repository
            .get_by_id(
                db,
                event_id,
            )
        )

        if not event:
            raise NotFoundException(
                "Operational event not found."
            )

        return event

    def list_events(
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
    ) -> OperationalEventListResponse:
        items = (
            operational_event_repository
            .list_filtered(
                db,
                source=source,
                severity=severity,
                event_type=event_type,
                is_resolved=is_resolved,
                correlation_id=correlation_id,
                user_id=user_id,
                background_job_id=(
                    background_job_id
                ),
                tryon_job_id=tryon_job_id,
                search=search,
                created_from=created_from,
                created_to=created_to,
                skip=skip,
                limit=limit,
            )
        )

        total = (
            operational_event_repository
            .count_filtered(
                db,
                source=source,
                severity=severity,
                event_type=event_type,
                is_resolved=is_resolved,
                correlation_id=correlation_id,
                user_id=user_id,
                background_job_id=(
                    background_job_id
                ),
                tryon_job_id=tryon_job_id,
                search=search,
                created_from=created_from,
                created_to=created_to,
            )
        )

        return OperationalEventListResponse(
            items=[
                self._response(item)
                for item in items
            ],
            total=total,
            skip=skip,
            limit=limit,
        )

    def resolve(
        self,
        db: Session,
        *,
        event_id: int,
        resolved_by_user_id: int,
        resolution_note: str,
    ) -> OperationalEventResponse:
        event = self.get(
            db,
            event_id=event_id,
        )

        event.is_resolved = True
        event.resolved_by_user_id = (
            resolved_by_user_id
        )
        event.resolved_at = utc_now()
        event.resolution_note = resolution_note

        db.add(event)
        db.commit()
        db.refresh(event)

        self.refresh_unresolved_metrics(db)

        return self._response(event)

    def summary(
        self,
        db: Session,
    ) -> OperationalEventSummaryResponse:
        rows = db.execute(
            select(
                OperationalEvent.severity,
                func.count(
                    OperationalEvent.id
                ),
            )
            .group_by(
                OperationalEvent.severity
            )
        ).all()

        source_rows = db.execute(
            select(
                OperationalEvent.source,
                func.count(
                    OperationalEvent.id
                ),
            )
            .group_by(
                OperationalEvent.source
            )
        ).all()

        counts = {
            str(severity): int(total)
            for severity, total in rows
        }

        total = sum(
            counts.values()
        )

        unresolved = int(
            db.execute(
                select(
                    func.count(
                        OperationalEvent.id
                    )
                ).where(
                    OperationalEvent
                    .is_resolved
                    .is_(False)
                )
            ).scalar_one()
        )

        self.refresh_unresolved_metrics(db)

        return OperationalEventSummaryResponse(
            total=total,
            unresolved=unresolved,
            info=counts.get("info", 0),
            warnings=counts.get(
                "warning",
                0,
            ),
            errors=counts.get(
                "error",
                0,
            ),
            critical=counts.get(
                "critical",
                0,
            ),
            by_source={
                str(source): int(count)
                for source, count
                in source_rows
            },
            generated_at=utc_now(),
        )

    def refresh_unresolved_metrics(
        self,
        db: Session,
    ) -> None:
        rows = db.execute(
            select(
                OperationalEvent.severity,
                func.count(
                    OperationalEvent.id
                ),
            )
            .where(
                OperationalEvent
                .is_resolved
                .is_(False)
            )
            .group_by(
                OperationalEvent.severity
            )
        ).all()

        values = {
            str(severity): int(total)
            for severity, total in rows
        }

        for severity in (
            "info",
            "warning",
            "error",
            "critical",
        ):
            OPERATIONAL_EVENTS_UNRESOLVED.labels(
                severity=severity
            ).set(
                values.get(
                    severity,
                    0,
                )
            )


operational_event_service = (
    OperationalEventService()
)