from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.rate_limit_enums import (
    RateLimitScope,
)
from app.common.time import utc_now
from app.core.redis_client import redis_client
from app.models.rate_limit_policy import RateLimitPolicy
from app.schemas.anti_abuse_operations import (
    AntiAbuseValidationItem,
    AntiAbuseValidationResponse,
)


class AntiAbuseValidationService:
    def _check(
        self,
        *,
        key: str,
        valid: bool,
        required: bool,
        message: str,
        metadata: dict | None = None,
    ) -> AntiAbuseValidationItem:
        return AntiAbuseValidationItem(
            key=key,
            valid=valid,
            required=required,
            message=message,
            metadata=metadata or {},
        )

    def validate(
        self,
        db: Session,
    ) -> AntiAbuseValidationResponse:
        checks: list[AntiAbuseValidationItem] = []

        redis_available = redis_client.ping()

        checks.append(
            self._check(
                key="redis_connection",
                valid=redis_available,
                required=True,
                message=(
                    "Redis connection is available."
                    if redis_available
                    else (
                        "Redis is unavailable. "
                        "Rate limiting will operate in fail-open mode."
                    )
                ),
            )
        )

        enabled_policy_count = int(
            db.execute(
                select(
                    func.count(RateLimitPolicy.id)
                ).where(
                    RateLimitPolicy.is_enabled.is_(True)
                )
            ).scalar_one()
        )

        checks.append(
            self._check(
                key="enabled_policies",
                valid=enabled_policy_count > 0,
                required=True,
                message=(
                    f"{enabled_policy_count} enabled "
                    "rate limit policy or policies found."
                    if enabled_policy_count > 0
                    else "No enabled rate limit policies exist."
                ),
                metadata={
                    "enabled_policy_count": (
                        enabled_policy_count
                    ),
                },
            )
        )

        login_policy_count = int(
            db.execute(
                select(
                    func.count(RateLimitPolicy.id)
                ).where(
                    RateLimitPolicy.is_enabled.is_(True),
                    RateLimitPolicy.route_pattern.in_(
                        [
                            "/api/v1/auth/login",
                            "/api/v1/auth/login*",
                        ]
                    ),
                )
            ).scalar_one()
        )

        checks.append(
            self._check(
                key="login_protection",
                valid=login_policy_count > 0,
                required=True,
                message=(
                    "Login endpoint has an enabled policy."
                    if login_policy_count > 0
                    else (
                        "Login endpoint has no enabled "
                        "rate limit policy."
                    )
                ),
            )
        )

        registration_policy_count = int(
            db.execute(
                select(
                    func.count(RateLimitPolicy.id)
                ).where(
                    RateLimitPolicy.is_enabled.is_(True),
                    RateLimitPolicy.route_pattern.in_(
                        [
                            "/api/v1/users",
                            "/api/v1/users/",
                            "/api/v1/users*",
                            "/api/v1/auth/register",
                        ]
                    ),
                )
            ).scalar_one()
        )

        checks.append(
            self._check(
                key="registration_protection",
                valid=registration_policy_count > 0,
                required=True,
                message=(
                    "Registration endpoint has an enabled policy."
                    if registration_policy_count > 0
                    else (
                        "Registration endpoint has no enabled "
                        "rate limit policy."
                    )
                ),
            )
        )

        tryon_policy_count = int(
            db.execute(
                select(
                    func.count(RateLimitPolicy.id)
                ).where(
                    RateLimitPolicy.is_enabled.is_(True),
                    RateLimitPolicy.route_pattern.like(
                        "%tryon%"
                    ),
                )
            ).scalar_one()
        )

        checks.append(
            self._check(
                key="tryon_protection",
                valid=tryon_policy_count > 0,
                required=True,
                message=(
                    "Try-on endpoints have an enabled policy."
                    if tryon_policy_count > 0
                    else (
                        "Try-on generation endpoints have no "
                        "enabled rate limit policy."
                    )
                ),
            )
        )

        invalid_policy_count = int(
            db.execute(
                select(
                    func.count(RateLimitPolicy.id)
                ).where(
                    (
                        RateLimitPolicy.request_limit <= 0
                    )
                    | (
                        RateLimitPolicy.window_seconds <= 0
                    )
                    | (
                        RateLimitPolicy.block_seconds < 0
                    )
                )
            ).scalar_one()
        )

        checks.append(
            self._check(
                key="policy_values",
                valid=invalid_policy_count == 0,
                required=True,
                message=(
                    "All policy values are valid."
                    if invalid_policy_count == 0
                    else (
                        f"{invalid_policy_count} policy or policies "
                        "contain invalid limits."
                    )
                ),
                metadata={
                    "invalid_policy_count": (
                        invalid_policy_count
                    ),
                },
            )
        )

        global_policy_count = int(
            db.execute(
                select(
                    func.count(RateLimitPolicy.id)
                ).where(
                    RateLimitPolicy.is_enabled.is_(True),
                    RateLimitPolicy.scope
                    == RateLimitScope.GLOBAL.value,
                )
            ).scalar_one()
        )

        checks.append(
            self._check(
                key="global_policy",
                valid=True,
                required=False,
                message=(
                    f"{global_policy_count} enabled global "
                    "policy or policies found."
                    if global_policy_count > 0
                    else (
                        "No global policy exists. "
                        "Endpoint-specific policies will still work."
                    )
                ),
            )
        )

        dangerously_low_count = int(
            db.execute(
                select(
                    func.count(RateLimitPolicy.id)
                ).where(
                    RateLimitPolicy.is_enabled.is_(True),
                    RateLimitPolicy.request_limit <= 1,
                    RateLimitPolicy.window_seconds >= 60,
                )
            ).scalar_one()
        )

        checks.append(
            self._check(
                key="dangerously_low_limits",
                valid=dangerously_low_count == 0,
                required=False,
                message=(
                    "No suspiciously low rate limits were detected."
                    if dangerously_low_count == 0
                    else (
                        f"{dangerously_low_count} enabled policy "
                        "or policies may block legitimate users."
                    )
                ),
                metadata={
                    "dangerously_low_count": (
                        dangerously_low_count
                    ),
                },
            )
        )

        required_checks = [
            check
            for check in checks
            if check.required
        ]

        ready = bool(required_checks) and all(
            check.valid
            for check in required_checks
        )

        return AntiAbuseValidationResponse(
            ready=ready,
            redis_available=redis_available,
            checks=checks,
            checked_at=utc_now(),
        )


anti_abuse_validation_service = (
    AntiAbuseValidationService()
)