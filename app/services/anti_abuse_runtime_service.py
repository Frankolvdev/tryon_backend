import hashlib
import json
import logging
from datetime import timedelta
from typing import Any

from fastapi import Request
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.common.rate_limit_enums import (
    AbuseEventType,
    AbuseSeverity,
    BlockTargetType,
)
from app.common.time import utc_now
from app.core.redis_client import redis_client
from app.schemas.rate_limit import SecurityBlockCreate
from app.schemas.rate_limit_runtime import RateLimitIdentity
from app.services.abuse_event_service import abuse_event_service
from app.services.security_block_service import security_block_service


logger = logging.getLogger(__name__)


class AntiAbuseRuntimeService:
    """
    Tracks endpoint-specific failures in Redis and escalates repeated
    suspicious activity to persistent security events and blocks.
    """

    RULES: dict[str, dict[str, Any]] = {
        "login_failure": {
            "event_type": AbuseEventType.LOGIN_BRUTE_FORCE,
            "severity": AbuseSeverity.HIGH,
            "limit": 5,
            "window_seconds": 900,
            "block_seconds": 1800,
            "persistent_block": True,
        },
        "refresh_failure": {
            "event_type": AbuseEventType.TOKEN_REFRESH_ABUSE,
            "severity": AbuseSeverity.HIGH,
            "limit": 10,
            "window_seconds": 600,
            "block_seconds": 1800,
            "persistent_block": True,
        },
        "registration_rejected": {
            "event_type": AbuseEventType.REGISTRATION_ABUSE,
            "severity": AbuseSeverity.MEDIUM,
            "limit": 10,
            "window_seconds": 3600,
            "block_seconds": 3600,
            "persistent_block": True,
        },
        "billing_checkout_rejected": {
            "event_type": AbuseEventType.PAYMENT_ABUSE,
            "severity": AbuseSeverity.HIGH,
            "limit": 10,
            "window_seconds": 600,
            "block_seconds": 1800,
            "persistent_block": False,
        },
        "tryon_rejected": {
            "event_type": AbuseEventType.TRYON_GENERATION_ABUSE,
            "severity": AbuseSeverity.MEDIUM,
            "limit": 20,
            "window_seconds": 300,
            "block_seconds": 600,
            "persistent_block": False,
        },
        "api_key_rejected": {
            "event_type": AbuseEventType.API_KEY_ABUSE,
            "severity": AbuseSeverity.HIGH,
            "limit": 15,
            "window_seconds": 600,
            "block_seconds": 1800,
            "persistent_block": True,
        },
    }

    def _hash(self, value: str) -> str:
        return hashlib.sha256(
            value.encode("utf-8")
        ).hexdigest()

    def _identity_value(
        self,
        identity: RateLimitIdentity,
    ) -> str:
        if identity.user_id is not None:
            return f"user:{identity.user_id}"

        if identity.api_key_id is not None:
            return f"api-key:{identity.api_key_id}"

        if identity.api_key_hash:
            return f"api-key-hash:{identity.api_key_hash}"

        return f"ip:{identity.ip_address or 'unknown'}"

    def _counter_key(
        self,
        *,
        rule_name: str,
        identity: RateLimitIdentity,
    ) -> str:
        identity_value = self._identity_value(identity)

        return (
            f"anti-abuse:"
            f"{rule_name}:"
            f"{self._hash(identity_value)}"
        )

    def _increment_counter(
        self,
        *,
        rule_name: str,
        identity: RateLimitIdentity,
        window_seconds: int,
    ) -> tuple[int, int]:
        client = redis_client.get_client()

        key = self._counter_key(
            rule_name=rule_name,
            identity=identity,
        )

        pipeline = client.pipeline()
        pipeline.incr(key)
        pipeline.ttl(key)

        count, ttl = pipeline.execute()

        if ttl is None or int(ttl) < 0:
            client.expire(
                key,
                window_seconds,
            )
            ttl = window_seconds

        return int(count), max(int(ttl), 1)

    def reset_counter(
        self,
        *,
        rule_name: str,
        identity: RateLimitIdentity,
    ) -> None:
        try:
            client = redis_client.get_client()

            client.delete(
                self._counter_key(
                    rule_name=rule_name,
                    identity=identity,
                )
            )

        except RedisError:
            logger.warning(
                "Could not reset anti-abuse counter: %s",
                rule_name,
            )

    def _block_target(
        self,
        identity: RateLimitIdentity,
    ) -> tuple[BlockTargetType, str] | None:
        if identity.user_id is not None:
            return (
                BlockTargetType.USER,
                str(identity.user_id),
            )

        if identity.api_key_id is not None:
            return (
                BlockTargetType.API_KEY,
                str(identity.api_key_id),
            )

        if identity.api_key_hash:
            return (
                BlockTargetType.API_KEY,
                identity.api_key_hash,
            )

        if identity.ip_address:
            return (
                BlockTargetType.IP,
                identity.ip_address,
            )

        return None

    def _create_persistent_block(
        self,
        db: Session,
        *,
        identity: RateLimitIdentity,
        abuse_event_id: int,
        reason: str,
        block_seconds: int,
        metadata: dict[str, Any],
    ) -> None:
        target = self._block_target(identity)

        if not target:
            return

        target_type, target_value = target

        try:
            security_block_service.create_block(
                db,
                data=SecurityBlockCreate(
                    target_type=target_type,
                    target_value=target_value,
                    reason=reason,
                    abuse_event_id=abuse_event_id,
                    expires_at=(
                        utc_now()
                        + timedelta(
                            seconds=block_seconds
                        )
                    ),
                    is_permanent=False,
                    metadata=metadata,
                ),
                created_by_user_id=None,
            )

        except Exception as error:
            db.rollback()

            # An existing active block is not a fatal problem.
            logger.warning(
                "Could not create automatic security block: %s",
                error,
            )

    def record_failure(
        self,
        db: Session,
        *,
        request: Request,
        identity: RateLimitIdentity,
        rule_name: str,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rule = self.RULES.get(rule_name)

        if not rule:
            return {
                "tracked": False,
                "reason": "unknown_rule",
            }

        try:
            count, ttl = self._increment_counter(
                rule_name=rule_name,
                identity=identity,
                window_seconds=rule["window_seconds"],
            )

        except RedisError as error:
            logger.warning(
                "Redis unavailable for anti-abuse tracking: %s",
                error,
            )

            return {
                "tracked": False,
                "redis_available": False,
                "error": str(error),
            }

        limit = int(rule["limit"])
        threshold_reached = count >= limit

        result = {
            "tracked": True,
            "rule": rule_name,
            "count": count,
            "limit": limit,
            "ttl": ttl,
            "threshold_reached": threshold_reached,
        }

        if not threshold_reached:
            return result

        event_details = {
            "rule": rule_name,
            "counter": count,
            "threshold": limit,
            "window_seconds": rule["window_seconds"],
            "block_seconds": rule["block_seconds"],
            "status_code": status_code,
            "route": request.url.path,
            "http_method": request.method.upper(),
            **(details or {}),
        }

        event = abuse_event_service.record_suspicious_request(
            db,
            event_type=rule["event_type"],
            severity=rule["severity"],
            request=request,
            identity=identity,
            details=event_details,
        )

        if bool(rule["persistent_block"]):
            self._create_persistent_block(
                db,
                identity=identity,
                abuse_event_id=event.id,
                reason=(
                    f"Automatic anti-abuse block generated by "
                    f"rule {rule_name}."
                ),
                block_seconds=int(
                    rule["block_seconds"]
                ),
                metadata={
                    "source": "anti_abuse_runtime",
                    "rule": rule_name,
                    "event_id": event.id,
                    "counter": count,
                },
            )

        # Prevent an abuse event from being created on every subsequent
        # request after the threshold has already been reached.
        self.reset_counter(
            rule_name=rule_name,
            identity=identity,
        )

        result["abuse_event_id"] = event.id
        result["persistent_block"] = bool(
            rule["persistent_block"]
        )

        return result


anti_abuse_runtime_service = AntiAbuseRuntimeService()