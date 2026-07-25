import logging
import time
from typing import Any

from starlette.types import (
    ASGIApp,
    Message,
    Receive,
    Scope,
    Send,
)

from app.observability.context import (
    get_correlation_id,
    set_request_context,
)


logger = logging.getLogger(
    "app.http"
)


class RequestLoggingMiddleware:
    def __init__(
        self,
        app: ASGIApp,
    ):
        self.app = app

    def _client_ip(
        self,
        scope: Scope,
    ) -> str | None:
        headers = {
            key.lower(): value
            for key, value
            in scope.get(
                "headers",
                [],
            )
        }

        forwarded_for = headers.get(
            b"x-forwarded-for"
        )

        if forwarded_for:
            try:
                value = forwarded_for.decode(
                    "utf-8"
                )

                return (
                    value.split(",")[0]
                    .strip()
                )

            except UnicodeDecodeError:
                pass

        client = scope.get("client")

        if client:
            return str(client[0])

        return None

    def _header(
        self,
        scope: Scope,
        name: bytes,
    ) -> str | None:
        for key, value in scope.get(
            "headers",
            [],
        ):
            if key.lower() != name:
                continue

            try:
                return value.decode(
                    "utf-8"
                )

            except UnicodeDecodeError:
                return None

        return None

    def _route_template(
        self,
        scope: Scope,
    ) -> str | None:
        route = scope.get("route")

        if route is None:
            return None

        return getattr(
            route,
            "path",
            None,
        )

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(
                scope,
                receive,
                send,
            )
            return

        started_at = time.perf_counter()

        method = scope.get(
            "method",
            "UNKNOWN",
        )

        path = scope.get(
            "path",
            "/",
        )

        query_string = scope.get(
            "query_string",
            b"",
        )

        try:
            decoded_query = query_string.decode(
                "utf-8"
            )
        except UnicodeDecodeError:
            decoded_query = ""

        request_data: dict[str, Any] = {
            "method": method,
            "path": path,
            "query": decoded_query or None,
            "client_ip": self._client_ip(
                scope
            ),
            "user_agent": self._header(
                scope,
                b"user-agent",
            ),
        }

        set_request_context(
            request_data
        )

        response_status = 500
        response_content_length: int | None = None

        async def send_wrapper(
            message: Message,
        ) -> None:
            nonlocal response_status
            nonlocal response_content_length

            if (
                message["type"]
                == "http.response.start"
            ):
                response_status = int(
                    message["status"]
                )

                for key, value in message.get(
                    "headers",
                    [],
                ):
                    if (
                        key.lower()
                        != b"content-length"
                    ):
                        continue

                    try:
                        response_content_length = int(
                            value.decode(
                                "ascii"
                            )
                        )
                    except (
                        ValueError,
                        UnicodeDecodeError,
                    ):
                        response_content_length = None

            await send(message)

        logger.info(
            "HTTP request started.",
            extra={
                "event": "http_request_started",
                "http_method": method,
                "http_path": path,
            },
        )

        try:
            await self.app(
                scope,
                receive,
                send_wrapper,
            )

        except Exception:
            duration_ms = round(
                (
                    time.perf_counter()
                    - started_at
                )
                * 1000,
                3,
            )

            logger.exception(
                "Unhandled exception during "
                "HTTP request.",
                extra={
                    "event": (
                        "http_request_failed"
                    ),
                    "http_method": method,
                    "http_path": path,
                    "http_status_code": 500,
                    "duration_ms": duration_ms,
                },
            )

            raise

        finally:
            duration_ms = round(
                (
                    time.perf_counter()
                    - started_at
                )
                * 1000,
                3,
            )

            request_data.update(
                {
                    "route": self._route_template(
                        scope
                    ),
                    "status_code": (
                        response_status
                    ),
                    "duration_ms": duration_ms,
                    "response_size_bytes": (
                        response_content_length
                    ),
                }
            )

            set_request_context(
                request_data
            )

            log_method = (
                logger.error
                if response_status >= 500
                else (
                    logger.warning
                    if response_status >= 400
                    else logger.info
                )
            )

            log_method(
                "HTTP request completed.",
                extra={
                    "event": (
                        "http_request_completed"
                    ),
                    "http_method": method,
                    "http_path": path,
                    "http_route": (
                        self._route_template(
                            scope
                        )
                    ),
                    "http_status_code": (
                        response_status
                    ),
                    "duration_ms": duration_ms,
                    "response_size_bytes": (
                        response_content_length
                    ),
                    "correlation_id": (
                        get_correlation_id()
                    ),
                },
            )