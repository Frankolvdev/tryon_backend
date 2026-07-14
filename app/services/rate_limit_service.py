from sqlalchemy.orm import Session

from app.models.rate_limit_policy import (
    RateLimitPolicy,
)
from app.schemas.rate_limit_runtime import (
    RateLimitCheckResult,
    RateLimitIdentity,
)
from app.services.rate_limit_engine_service import (
    rate_limit_engine_service,
)
from app.services.rate_limit_policy_service import (
    rate_limit_policy_service,
)


class RateLimitService:
    def find_policy(
        self,
        db: Session,
        *,
        route: str,
        http_method: str,
        identity: RateLimitIdentity,
    ) -> RateLimitPolicy | None:
        return rate_limit_policy_service.match_policy(
            db,
            route=route,
            http_method=http_method,
            is_authenticated=(
                identity.is_authenticated
            ),
        )

    def check_request_with_policy(
        self,
        db: Session,
        *,
        route: str,
        identity: RateLimitIdentity,
        policy: RateLimitPolicy,
    ) -> RateLimitCheckResult:
        return rate_limit_engine_service.check(
            db,
            policy=policy,
            identity=identity,
            route=route,
        )

    def check_request(
        self,
        db: Session,
        *,
        route: str,
        http_method: str,
        identity: RateLimitIdentity,
    ) -> RateLimitCheckResult | None:
        policy = self.find_policy(
            db,
            route=route,
            http_method=http_method,
            identity=identity,
        )

        if not policy:
            return None

        return self.check_request_with_policy(
            db,
            route=route,
            identity=identity,
            policy=policy,
        )

    def response_headers(
        self,
        *,
        result: RateLimitCheckResult,
    ) -> dict[str, str]:
        return rate_limit_engine_service.headers(
            result=result,
        )


rate_limit_service = RateLimitService()