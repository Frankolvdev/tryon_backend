from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.rate_limit_enums import (
    AbuseEventStatus,
    AbuseSeverity,
)
from app.common.time import utc_now
from app.models.abuse_event import AbuseEvent
from app.models.rate_limit_policy import RateLimitPolicy
from app.models.security_block import SecurityBlock
from app.schemas.anti_abuse_operations import (
    AntiAbuseEventTypeMetric,
    AntiAbuseMetricsResponse,
    AntiAbuseSeverityMetric,
    AntiAbuseStatusMetric,
)


class AntiAbuseMetricsService:
    def _resolve_period(
        self,
        *,
        start: datetime | None,
        end: datetime | None,
    ) -> tuple[datetime, datetime]:
        resolved_end = end or utc_now()
        resolved_start = start or (
            resolved_end - timedelta(days=30)
        )

        if resolved_start >= resolved_end:
            raise ValueError(
                "Metrics start date must be earlier than end date."
            )

        return resolved_start, resolved_end

    def _event_count(
        self,
        db: Session,
        *,
        start: datetime,
        end: datetime,
        status: str | None = None,
        severity: str | None = None,
    ) -> int:
        statement = (
            select(func.count(AbuseEvent.id))
            .where(AbuseEvent.created_at >= start)
            .where(AbuseEvent.created_at < end)
        )

        if status is not None:
            statement = statement.where(
                AbuseEvent.status == status
            )

        if severity is not None:
            statement = statement.where(
                AbuseEvent.severity == severity
            )

        return int(db.execute(statement).scalar_one())

    def _group_events(
        self,
        db: Session,
        *,
        column,
        start: datetime,
        end: datetime,
    ) -> list[tuple[str, int]]:
        statement = (
            select(
                column,
                func.count(AbuseEvent.id),
            )
            .where(AbuseEvent.created_at >= start)
            .where(AbuseEvent.created_at < end)
            .group_by(column)
            .order_by(func.count(AbuseEvent.id).desc())
        )

        return [
            (
                str(value),
                int(total),
            )
            for value, total in db.execute(statement).all()
        ]

    def get_metrics(
        self,
        db: Session,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> AntiAbuseMetricsResponse:
        period_start, period_end = self._resolve_period(
            start=start,
            end=end,
        )

        now = utc_now()

        active_blocks = int(
            db.execute(
                select(func.count(SecurityBlock.id)).where(
                    SecurityBlock.is_active.is_(True),
                    SecurityBlock.starts_at <= now,
                    (
                        SecurityBlock.is_permanent.is_(True)
                        | SecurityBlock.expires_at.is_(None)
                        | (SecurityBlock.expires_at > now)
                    ),
                )
            ).scalar_one()
        )

        temporary_blocks = int(
            db.execute(
                select(func.count(SecurityBlock.id)).where(
                    SecurityBlock.is_active.is_(True),
                    SecurityBlock.is_permanent.is_(False),
                    SecurityBlock.expires_at.is_not(None),
                    SecurityBlock.expires_at > now,
                )
            ).scalar_one()
        )

        permanent_blocks = int(
            db.execute(
                select(func.count(SecurityBlock.id)).where(
                    SecurityBlock.is_active.is_(True),
                    SecurityBlock.is_permanent.is_(True),
                )
            ).scalar_one()
        )

        expired_active_blocks = int(
            db.execute(
                select(func.count(SecurityBlock.id)).where(
                    SecurityBlock.is_active.is_(True),
                    SecurityBlock.is_permanent.is_(False),
                    SecurityBlock.expires_at.is_not(None),
                    SecurityBlock.expires_at <= now,
                )
            ).scalar_one()
        )

        enabled_policies = int(
            db.execute(
                select(
                    func.count(RateLimitPolicy.id)
                ).where(
                    RateLimitPolicy.is_enabled.is_(True)
                )
            ).scalar_one()
        )

        disabled_policies = int(
            db.execute(
                select(
                    func.count(RateLimitPolicy.id)
                ).where(
                    RateLimitPolicy.is_enabled.is_(False)
                )
            ).scalar_one()
        )

        event_types = self._group_events(
            db,
            column=AbuseEvent.event_type,
            start=period_start,
            end=period_end,
        )

        severities = self._group_events(
            db,
            column=AbuseEvent.severity,
            start=period_start,
            end=period_end,
        )

        statuses = self._group_events(
            db,
            column=AbuseEvent.status,
            start=period_start,
            end=period_end,
        )

        return AntiAbuseMetricsResponse(
            total_events=self._event_count(
                db,
                start=period_start,
                end=period_end,
            ),
            open_events=self._event_count(
                db,
                start=period_start,
                end=period_end,
                status=AbuseEventStatus.OPEN.value,
            ),
            reviewed_events=self._event_count(
                db,
                start=period_start,
                end=period_end,
                status=AbuseEventStatus.REVIEWED.value,
            ),
            resolved_events=self._event_count(
                db,
                start=period_start,
                end=period_end,
                status=AbuseEventStatus.RESOLVED.value,
            ),
            ignored_events=self._event_count(
                db,
                start=period_start,
                end=period_end,
                status=AbuseEventStatus.IGNORED.value,
            ),
            low_severity_events=self._event_count(
                db,
                start=period_start,
                end=period_end,
                severity=AbuseSeverity.LOW.value,
            ),
            medium_severity_events=self._event_count(
                db,
                start=period_start,
                end=period_end,
                severity=AbuseSeverity.MEDIUM.value,
            ),
            high_severity_events=self._event_count(
                db,
                start=period_start,
                end=period_end,
                severity=AbuseSeverity.HIGH.value,
            ),
            critical_severity_events=self._event_count(
                db,
                start=period_start,
                end=period_end,
                severity=AbuseSeverity.CRITICAL.value,
            ),
            active_blocks=active_blocks,
            temporary_blocks=temporary_blocks,
            permanent_blocks=permanent_blocks,
            expired_active_blocks=expired_active_blocks,
            enabled_policies=enabled_policies,
            disabled_policies=disabled_policies,
            events_by_type=[
                AntiAbuseEventTypeMetric(
                    event_type=event_type,
                    total=total,
                )
                for event_type, total in event_types
            ],
            events_by_severity=[
                AntiAbuseSeverityMetric(
                    severity=severity,
                    total=total,
                )
                for severity, total in severities
            ],
            events_by_status=[
                AntiAbuseStatusMetric(
                    status=status,
                    total=total,
                )
                for status, total in statuses
            ],
            period_start=period_start,
            period_end=period_end,
            generated_at=utc_now(),
        )


anti_abuse_metrics_service = AntiAbuseMetricsService()