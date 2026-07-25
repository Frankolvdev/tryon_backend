import logging
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from app.db.database import SessionLocal
from app.models.rate_limit_policy import RateLimitPolicy
from app.schemas.rate_limit_runtime import (
    RateLimitCheckResult,
)
from app.services.abuse_event_service import (
    abuse_event_service,
)
from app.services.rate_limit_identity_service import (
    rate_limit_identity_service,
)
from app.services.rate_limit_service import (
    rate_limit_service,
)
from app.services.security_block_service import (
    security_block_service,
)

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    EXCLUDED_EXACT_PATHS = {
        "/",
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/v1/health",
        "/api/v1/db-health",
    }

    EXCLUDED_PREFIXES = (
        "/docs/",
        "/redoc/",
        "/static/",
    )

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[
            [Request],
            Awaitable[Response],
        ],
    ) -> Response:
        if self._should_skip(request):
            return await call_next(request)

        db: Session = SessionLocal()

        try:
            identity = (
                rate_limit_identity_service.resolve(
                    request
                )
            )

            request.state.rate_limit_identity = (
                identity
            )

            administrative_block = (
                security_block_service.find_identity_block(
                    db,
                    identity=identity,
                )
            )

            if administrative_block:
                return self._security_block_response(
                    request=request,
                    block=administrative_block,
                )

            policy = rate_limit_service.find_policy(
                db,
                route=request.url.path,
                http_method=request.method,
                identity=identity,
            )

            if not policy:
                return await call_next(request)

            result = (
                rate_limit_service.check_request_with_policy(
                    db,
                    route=request.url.path,
                    identity=identity,
                    policy=policy,
                )
            )

            request.state.rate_limit_result = result
            request.state.rate_limit_policy = policy

            if not result.allowed:
                self._record_violation_safely(
                    db=db,
                    request=request,
                    policy=policy,
                    identity=identity,
                    result=result,
                )

                return self._rate_limit_response(
                    request=request,
                    result=result,
                )

            response = await call_next(request)

            if policy.include_headers:
                self._add_headers(
                    response=response,
                    result=result,
                )

            return response

        except Exception as error:
            logger.exception(
                "Rate limit middleware failed open: %s",
                error,
            )

            request.state.rate_limit_error = str(error)

            return await call_next(request)

        finally:
            db.close()

    def _record_violation_safely(
        self,
        *,
        db: Session,
        request: Request,
        policy: RateLimitPolicy,
        identity,
        result: RateLimitCheckResult,
    ) -> None:
        try:
            event = (
                abuse_event_service
                .record_rate_limit_violation(
                    db,
                    request=request,
                    policy=policy,
                    identity=identity,
                    result=result,
                )
            )

            automatic_persistent_block = bool(
                self._policy_metadata(
                    policy
                ).get(
                    "create_security_block",
                    False,
                )
            )

            if (
                automatic_persistent_block
                and result.blocked
                and result.blocked_until
            ):
                security_block_service.block_from_rate_limit_event(
                    db,
                    abuse_event_id=event.id,
                    identity=identity,
                    reason=(
                        f"Automatic block caused by "
                        f"rate limit policy {policy.key}."
                    ),
                    expires_at=result.blocked_until,
                )

        except Exception as error:
            db.rollback()

            logger.exception(
                "Could not persist abuse event: %s",
                error,
            )

    def _policy_metadata(
        self,
        policy: RateLimitPolicy,
    ) -> dict:
        import json

        if not policy.metadata_json:
            return {}

        try:
            parsed = json.loads(
                policy.metadata_json
            )

            return (
                parsed
                if isinstance(parsed, dict)
                else {}
            )
        except (json.JSONDecodeError, TypeError):
            return {}

    def _should_skip(
        self,
        request: Request,
    ) -> bool:
        path = request.url.path

        if request.method.upper() == "OPTIONS":
            return True

        if path in self.EXCLUDED_EXACT_PATHS:
            return True

        if any(
            path.startswith(prefix)
            for prefix in self.EXCLUDED_PREFIXES
        ):
            return True

        if not path.startswith("/api/v1"):
            return True

        return False

    def _security_block_response(
        self,
        *,
        request: Request,
        block,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "error": {
                    "code": "security_blocked",
                    "message": (
                        "Access has been blocked by a "
                        "security policy."
                    ),
                    "details": {
                        "target_type": (
                            block.target_type
                        ),
                        "reason": block.reason,
                        "is_permanent": (
                            block.is_permanent
                        ),
                        "expires_at": (
                            block.expires_at.isoformat()
                            if block.expires_at
                            else None
                        ),
                    },
                },
                "path": request.url.path,
            },
        )

    def _rate_limit_response(
        self,
        *,
        request: Request,
        result: RateLimitCheckResult,
    ) -> JSONResponse:
        response = JSONResponse(
            status_code=429,
            content={
                "success": False,
                "error": {
                    "code": "rate_limit_exceeded",
                    "message": (
                        "Too many requests. "
                        "Please try again later."
                    ),
                    "details": {
                        "policy": result.policy_key,
                        "limit": result.request_limit,
                        "remaining": result.remaining,
                        "window_seconds": (
                            result.window_seconds
                        ),
                        "retry_after_seconds": (
                            result.retry_after_seconds
                        ),
                        "blocked": result.blocked,
                        "blocked_until": (
                            result.blocked_until.isoformat()
                            if result.blocked_until
                            else None
                        ),
                    },
                },
                "path": request.url.path,
            },
        )

        self._add_headers(
            response=response,
            result=result,
        )

        return response

    def _add_headers(
        self,
        *,
        response: Response,
        result: RateLimitCheckResult,
    ) -> None:
        headers = rate_limit_service.response_headers(
            result=result,
        )

        for header_name, header_value in headers.items():
            response.headers[header_name] = header_value

        response.headers[
            "X-RateLimit-Redis-Available"
        ] = (
            "true"
            if result.redis_available
            else "false"
        )

        if result.fallback_used:
            response.headers[
                "X-RateLimit-Fallback"
            ] = "true"