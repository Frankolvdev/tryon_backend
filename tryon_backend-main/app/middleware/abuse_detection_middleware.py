import logging
from collections.abc import Awaitable, Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.db.database import SessionLocal
from app.schemas.rate_limit_runtime import RateLimitIdentity
from app.services.anti_abuse_runtime_service import (
    anti_abuse_runtime_service,
)
from app.services.rate_limit_identity_service import (
    rate_limit_identity_service,
)


logger = logging.getLogger(__name__)


class AbuseDetectionMiddleware(BaseHTTPMiddleware):
    """
    Observes endpoint responses and tracks repeated suspicious failures.

    This middleware does not replace RateLimitMiddleware. It complements
    it by evaluating the semantic result of protected operations.
    """

    LOGIN_PATHS = {
        "/api/v1/auth/login",
    }

    REFRESH_PATHS = {
        "/api/v1/auth/refresh",
    }

    REGISTRATION_PATHS = {
        "/api/v1/users",
        "/api/v1/users/",
        "/api/v1/auth/register",
    }

    API_KEY_PATH_PREFIXES = (
        "/api/v1/api-keys",
        "/api/v1/admin/api-keys",
    )

    BILLING_CHECKOUT_PATHS = {
        "/api/v1/billing/checkout/tokens",
        "/api/v1/billing/subscriptions/checkout",
    }

    TRYON_PATH_PREFIXES = (
        "/api/v1/tryon",
    )

    AUTH_FAILURE_STATUS_CODES = {
        400,
        401,
        403,
    }

    REGISTRATION_REJECTION_STATUS_CODES = {
        409,
        422,
        429,
    }

    CHECKOUT_REJECTION_STATUS_CODES = {
        400,
        402,
        403,
        409,
        422,
        429,
    }

    TRYON_REJECTION_STATUS_CODES = {
        400,
        402,
        403,
        409,
        422,
        429,
    }

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[
            [Request],
            Awaitable[Response],
        ],
    ) -> Response:
        response = await call_next(request)

        if self._should_skip(request):
            return response

        identity = self._resolve_identity(request)

        rule_name = self._resolve_rule(
            request=request,
            status_code=response.status_code,
        )

        if not rule_name:
            self._handle_success(
                request=request,
                identity=identity,
                status_code=response.status_code,
            )

            return response

        db = SessionLocal()

        try:
            tracking_result = (
                anti_abuse_runtime_service.record_failure(
                    db,
                    request=request,
                    identity=identity,
                    rule_name=rule_name,
                    status_code=response.status_code,
                    details={
                        "user_agent": request.headers.get(
                            "user-agent"
                        ),
                        "origin": request.headers.get(
                            "origin"
                        ),
                        "referer": request.headers.get(
                            "referer"
                        ),
                    },
                )
            )

            request.state.anti_abuse_result = (
                tracking_result
            )

            if tracking_result.get(
                "threshold_reached"
            ):
                response.headers[
                    "X-Anti-Abuse-Threshold"
                ] = "reached"

                response.headers[
                    "X-Anti-Abuse-Rule"
                ] = rule_name

        except Exception as error:
            db.rollback()

            logger.exception(
                "Anti-abuse observation failed open: %s",
                error,
            )

            request.state.anti_abuse_error = str(
                error
            )

        finally:
            db.close()

        return response

    def _should_skip(
        self,
        request: Request,
    ) -> bool:
        if request.method.upper() == "OPTIONS":
            return True

        return not request.url.path.startswith(
            "/api/v1"
        )

    def _resolve_identity(
        self,
        request: Request,
    ) -> RateLimitIdentity:
        existing = getattr(
            request.state,
            "rate_limit_identity",
            None,
        )

        if isinstance(existing, RateLimitIdentity):
            return existing

        return rate_limit_identity_service.resolve(
            request
        )

    def _resolve_rule(
        self,
        *,
        request: Request,
        status_code: int,
    ) -> str | None:
        path = request.url.path
        method = request.method.upper()

        if (
            path in self.LOGIN_PATHS
            and method == "POST"
            and status_code
            in self.AUTH_FAILURE_STATUS_CODES
        ):
            return "login_failure"

        if (
            path in self.REFRESH_PATHS
            and method == "POST"
            and status_code
            in self.AUTH_FAILURE_STATUS_CODES
        ):
            return "refresh_failure"

        if (
            path in self.REGISTRATION_PATHS
            and method == "POST"
            and status_code
            in self.REGISTRATION_REJECTION_STATUS_CODES
        ):
            return "registration_rejected"

        if (
            path in self.BILLING_CHECKOUT_PATHS
            and method == "POST"
            and status_code
            in self.CHECKOUT_REJECTION_STATUS_CODES
        ):
            return "billing_checkout_rejected"

        if (
            method == "POST"
            and any(
                path.startswith(prefix)
                for prefix in self.TRYON_PATH_PREFIXES
            )
            and status_code
            in self.TRYON_REJECTION_STATUS_CODES
        ):
            return "tryon_rejected"

        if (
            any(
                path.startswith(prefix)
                for prefix in self.API_KEY_PATH_PREFIXES
            )
            and status_code
            in self.AUTH_FAILURE_STATUS_CODES
        ):
            return "api_key_rejected"

        return None

    def _handle_success(
        self,
        *,
        request: Request,
        identity: RateLimitIdentity,
        status_code: int,
    ) -> None:
        if status_code < 200 or status_code >= 300:
            return

        path = request.url.path

        if path in self.LOGIN_PATHS:
            anti_abuse_runtime_service.reset_counter(
                rule_name="login_failure",
                identity=identity,
            )

        if path in self.REFRESH_PATHS:
            anti_abuse_runtime_service.reset_counter(
                rule_name="refresh_failure",
                identity=identity,
            )