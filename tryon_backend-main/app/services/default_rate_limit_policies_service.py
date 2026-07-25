from sqlalchemy.orm import Session

from app.common.rate_limit_enums import (
    RateLimitAlgorithm,
    RateLimitScope,
)
from app.repositories.rate_limit_policy_repository import (
    rate_limit_policy_repository,
)
from app.schemas.rate_limit import RateLimitPolicyCreate
from app.services.rate_limit_policy_service import (
    rate_limit_policy_service,
)


class DefaultRateLimitPoliciesService:
    def seed_defaults(
        self,
        db: Session,
    ) -> dict:
        defaults = [
            RateLimitPolicyCreate(
                key="global_anonymous",
                name="Global anonymous traffic",
                description=(
                    "General protection for anonymous requests."
                ),
                route_pattern="/api/v1/*",
                http_method=None,
                scope=RateLimitScope.IP,
                algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
                request_limit=300,
                window_seconds=60,
                burst_limit=400,
                block_seconds=60,
                priority=1000,
                applies_to_authenticated=False,
                applies_to_anonymous=True,
                include_headers=True,
                is_enabled=True,
                metadata={
                    "category": "global",
                },
            ),
            RateLimitPolicyCreate(
                key="auth_login_ip",
                name="Login attempts per IP",
                description=(
                    "Limits repeated authentication attempts."
                ),
                route_pattern="/api/v1/auth/login",
                http_method="POST",
                scope=RateLimitScope.IP,
                algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
                request_limit=10,
                window_seconds=300,
                burst_limit=12,
                block_seconds=900,
                priority=10,
                applies_to_authenticated=True,
                applies_to_anonymous=True,
                include_headers=True,
                is_enabled=True,
                metadata={
                    "abuse_event_type": (
                        "login_brute_force"
                    ),
                    "severity": "high",
                },
            ),
            RateLimitPolicyCreate(
                key="auth_register_ip",
                name="Registrations per IP",
                description=(
                    "Prevents mass account creation."
                ),
                route_pattern="/api/v1/users/",
                http_method="POST",
                scope=RateLimitScope.IP,
                algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
                request_limit=5,
                window_seconds=3600,
                burst_limit=5,
                block_seconds=3600,
                priority=20,
                applies_to_authenticated=True,
                applies_to_anonymous=True,
                include_headers=True,
                is_enabled=True,
                metadata={
                    "abuse_event_type": (
                        "registration_abuse"
                    ),
                    "severity": "high",
                },
            ),
            RateLimitPolicyCreate(
                key="auth_refresh",
                name="Token refresh",
                description=(
                    "Limits refresh token requests."
                ),
                route_pattern="/api/v1/auth/refresh",
                http_method="POST",
                scope=RateLimitScope.IP,
                algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
                request_limit=30,
                window_seconds=300,
                burst_limit=40,
                block_seconds=300,
                priority=30,
                applies_to_authenticated=True,
                applies_to_anonymous=True,
                include_headers=True,
                is_enabled=True,
                metadata={
                    "abuse_event_type": (
                        "token_refresh_abuse"
                    ),
                    "severity": "medium",
                },
            ),
            RateLimitPolicyCreate(
                key="tryon_user",
                name="Try-on creation per user",
                description=(
                    "Prevents excessive generation requests."
                ),
                route_pattern="/api/v1/tryon*",
                http_method="POST",
                scope=RateLimitScope.USER,
                algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
                request_limit=30,
                window_seconds=60,
                burst_limit=40,
                block_seconds=120,
                priority=40,
                applies_to_authenticated=True,
                applies_to_anonymous=False,
                include_headers=True,
                is_enabled=True,
                metadata={
                    "abuse_event_type": (
                        "tryon_generation_abuse"
                    ),
                    "severity": "medium",
                },
            ),
            RateLimitPolicyCreate(
                key="billing_checkout_user",
                name="Billing Checkout per user",
                description=(
                    "Limits repeated Checkout Session creation."
                ),
                route_pattern="/api/v1/billing/*checkout*",
                http_method="POST",
                scope=RateLimitScope.USER,
                algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
                request_limit=10,
                window_seconds=300,
                burst_limit=12,
                block_seconds=600,
                priority=50,
                applies_to_authenticated=True,
                applies_to_anonymous=False,
                include_headers=True,
                is_enabled=True,
                metadata={
                    "abuse_event_type": "payment_abuse",
                    "severity": "high",
                },
            ),
            RateLimitPolicyCreate(
                key="stripe_webhook_ip",
                name="Stripe webhook traffic",
                description=(
                    "Protects the Stripe webhook endpoint "
                    "against request floods."
                ),
                route_pattern="/api/v1/webhooks/stripe",
                http_method="POST",
                scope=RateLimitScope.IP,
                algorithm=RateLimitAlgorithm.FIXED_WINDOW,
                request_limit=500,
                window_seconds=60,
                burst_limit=700,
                block_seconds=60,
                priority=5,
                applies_to_authenticated=True,
                applies_to_anonymous=True,
                include_headers=False,
                is_enabled=True,
                metadata={
                    "abuse_event_type": "webhook_abuse",
                    "severity": "high",
                },
            ),
        ]

        created = 0
        skipped = 0

        for item in defaults:
            existing = (
                rate_limit_policy_repository.get_by_key(
                    db,
                    item.key,
                )
            )

            if existing:
                skipped += 1
                continue

            rate_limit_policy_service.create_policy(
                db,
                data=item,
            )

            created += 1

        return {
            "created": created,
            "skipped": skipped,
            "total": len(defaults),
        }


default_rate_limit_policies_service = (
    DefaultRateLimitPoliciesService()
)