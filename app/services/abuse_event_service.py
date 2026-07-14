import json
from datetime import timedelta
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.common.rate_limit_enums import (
    AbuseEventStatus,
    AbuseEventType,
    AbuseSeverity,
    BlockTargetType,
)
from app.common.time import utc_now
from app.models.abuse_event import AbuseEvent
from app.models.rate_limit_policy import RateLimitPolicy
from app.repositories.abuse_event_repository import (
    abuse_event_repository,
)
from app.schemas.rate_limit import (
    AbuseEventListResponse,
    AbuseEventResponse,
    AbuseEventReviewRequest,
)
from app.schemas.rate_limit_runtime import (
    RateLimitCheckResult,
    RateLimitIdentity,
)


class AbuseEventService:
    def _serialize_json(self, value: Any) -> str:
        return json.dumps(
            value or {},
            ensure_ascii=False,
            default=str,
        )

    def _parse_json(
        self,
        value: str | None,
    ) -> dict[str, Any]:
        if not value:
            return {}

        try:
            parsed = json.loads(value)

            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _to_response(
        self,
        event: AbuseEvent,
    ) -> AbuseEventResponse:
        return AbuseEventResponse(
            id=event.id,
            event_type=event.event_type,
            severity=event.severity,
            status=event.status,
            rate_limit_policy_id=event.rate_limit_policy_id,
            user_id=event.user_id,
            api_key_id=event.api_key_id,
            ip_address=event.ip_address,
            user_agent=event.user_agent,
            route=event.route,
            http_method=event.http_method,
            identifier=event.identifier,
            request_count=event.request_count,
            request_limit=event.request_limit,
            window_seconds=event.window_seconds,
            blocked_until=event.blocked_until,
            details=self._parse_json(event.details_json),
            reviewed_by_user_id=event.reviewed_by_user_id,
            reviewed_at=event.reviewed_at,
            resolution_notes=event.resolution_notes,
            created_at=event.created_at,
            updated_at=event.updated_at,
        )

    def get_event(
        self,
        db: Session,
        *,
        event_id: int,
    ) -> AbuseEvent:
        event = abuse_event_repository.get_by_id(
            db,
            event_id,
        )

        if not event:
            from app.common.exceptions import NotFoundException

            raise NotFoundException(
                "Abuse event not found."
            )

        return event

    def get_response(
        self,
        db: Session,
        *,
        event_id: int,
    ) -> AbuseEventResponse:
        return self._to_response(
            self.get_event(
                db,
                event_id=event_id,
            )
        )

    def list_events(
        self,
        db: Session,
        *,
        event_type: AbuseEventType | None = None,
        severity: AbuseSeverity | None = None,
        status: AbuseEventStatus | None = None,
        user_id: int | None = None,
        ip_address: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> AbuseEventListResponse:
        events = abuse_event_repository.list_filtered(
            db,
            event_type=(
                event_type.value
                if event_type
                else None
            ),
            severity=(
                severity.value
                if severity
                else None
            ),
            status=(
                status.value
                if status
                else None
            ),
            user_id=user_id,
            ip_address=ip_address,
            skip=skip,
            limit=limit,
        )

        total = abuse_event_repository.count_filtered(
            db,
            event_type=(
                event_type.value
                if event_type
                else None
            ),
            severity=(
                severity.value
                if severity
                else None
            ),
            status=(
                status.value
                if status
                else None
            ),
            user_id=user_id,
            ip_address=ip_address,
        )

        return AbuseEventListResponse(
            items=[
                self._to_response(event)
                for event in events
            ],
            total=total,
            skip=skip,
            limit=limit,
        )

    def _metadata_value(
        self,
        policy: RateLimitPolicy,
        key: str,
        default: str,
    ) -> str:
        metadata = self._parse_json(
            policy.metadata_json
        )

        value = metadata.get(key)

        return str(value) if value else default

    def _event_type_for_policy(
        self,
        policy: RateLimitPolicy,
    ) -> str:
        value = self._metadata_value(
            policy,
            "abuse_event_type",
            AbuseEventType.RATE_LIMIT_EXCEEDED.value,
        )

        valid_values = {
            item.value
            for item in AbuseEventType
        }

        if value not in valid_values:
            return AbuseEventType.RATE_LIMIT_EXCEEDED.value

        return value

    def _severity_for_policy(
        self,
        policy: RateLimitPolicy,
        result: RateLimitCheckResult,
    ) -> str:
        configured = self._metadata_value(
            policy,
            "severity",
            AbuseSeverity.MEDIUM.value,
        )

        valid_values = {
            item.value
            for item in AbuseSeverity
        }

        if configured not in valid_values:
            configured = AbuseSeverity.MEDIUM.value

        if result.blocked:
            if configured == AbuseSeverity.LOW.value:
                return AbuseSeverity.MEDIUM.value

            if configured == AbuseSeverity.MEDIUM.value:
                return AbuseSeverity.HIGH.value

        return configured

    def record_rate_limit_violation(
        self,
        db: Session,
        *,
        request: Request,
        policy: RateLimitPolicy,
        identity: RateLimitIdentity,
        result: RateLimitCheckResult,
    ) -> AbuseEvent:
        blocked_until = result.blocked_until

        if (
            blocked_until is None
            and result.retry_after_seconds > 0
        ):
            blocked_until = utc_now() + timedelta(
                seconds=result.retry_after_seconds
            )

        event = AbuseEvent(
            event_type=self._event_type_for_policy(
                policy
            ),
            severity=self._severity_for_policy(
                policy,
                result,
            ),
            status=AbuseEventStatus.OPEN.value,
            rate_limit_policy_id=policy.id,
            user_id=identity.user_id,
            api_key_id=identity.api_key_id,
            ip_address=identity.ip_address,
            user_agent=request.headers.get(
                "user-agent"
            ),
            route=request.url.path,
            http_method=request.method.upper(),
            identifier=result.identifier,
            request_count=result.request_count,
            request_limit=result.request_limit,
            window_seconds=result.window_seconds,
            blocked_until=blocked_until,
            details_json=self._serialize_json(
                {
                    "policy_key": policy.key,
                    "algorithm": policy.algorithm,
                    "action": result.action.value,
                    "redis_available": (
                        result.redis_available
                    ),
                    "fallback_used": (
                        result.fallback_used
                    ),
                    "query_string": (
                        request.url.query or None
                    ),
                    "request_headers": {
                        "content_type": request.headers.get(
                            "content-type"
                        ),
                        "origin": request.headers.get(
                            "origin"
                        ),
                        "referer": request.headers.get(
                            "referer"
                        ),
                    },
                    "rate_limit_metadata": (
                        result.metadata
                    ),
                }
            ),
        )

        db.add(event)
        db.commit()
        db.refresh(event)

        return event

    def record_suspicious_request(
        self,
        db: Session,
        *,
        event_type: AbuseEventType,
        severity: AbuseSeverity,
        request: Request,
        identity: RateLimitIdentity,
        details: dict[str, Any] | None = None,
    ) -> AbuseEvent:
        event = AbuseEvent(
            event_type=event_type.value,
            severity=severity.value,
            status=AbuseEventStatus.OPEN.value,
            user_id=identity.user_id,
            api_key_id=identity.api_key_id,
            ip_address=identity.ip_address,
            user_agent=request.headers.get(
                "user-agent"
            ),
            route=request.url.path,
            http_method=request.method.upper(),
            identifier=(
                f"user:{identity.user_id}"
                if identity.user_id is not None
                else f"ip:{identity.ip_address}"
            ),
            details_json=self._serialize_json(
                details or {}
            ),
        )

        db.add(event)
        db.commit()
        db.refresh(event)

        return event

    def review_event(
        self,
        db: Session,
        *,
        event_id: int,
        reviewer_user_id: int,
        data: AbuseEventReviewRequest,
    ) -> AbuseEventResponse:
        event = self.get_event(
            db,
            event_id=event_id,
        )

        event.status = data.status.value
        event.reviewed_by_user_id = (
            reviewer_user_id
        )
        event.reviewed_at = utc_now()
        event.resolution_notes = (
            data.resolution_notes
        )

        db.add(event)
        db.commit()
        db.refresh(event)

        return self._to_response(event)


abuse_event_service = AbuseEventService()