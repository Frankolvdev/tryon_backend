from __future__ import annotations

import logging
import os
import time
from urllib.parse import parse_qsl, urlencode

from starlette.types import ASGIApp, Message, Receive, Scope, Send


logger = logging.getLogger("uvicorn.error")

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _timing_logs_enabled() -> bool:
    """Resolve REQUEST_TIMING_LOGS without making production noisy by default.

    Explicit REQUEST_TIMING_LOGS always wins. If it is omitted, timing logs are
    enabled outside production and disabled in production.
    """
    explicit = os.getenv("REQUEST_TIMING_LOGS")
    if explicit is not None:
        normalized = explicit.strip().lower()
        if normalized in _TRUE_VALUES:
            return True
        if normalized in _FALSE_VALUES:
            return False
        logger.warning(
            "Invalid REQUEST_TIMING_LOGS=%r; using environment-safe default.",
            explicit,
        )

    app_env = os.getenv("APP_ENV", "development").strip().lower()
    return app_env != "production"

_SENSITIVE_QUERY_KEYS = {
    "access_token",
    "authorization",
    "code",
    "id_token",
    "jwt",
    "password",
    "refresh_token",
    "secret",
    "token",
}


class PerformanceTimingMiddleware:
    """Print one human-readable timing line for every HTTP request.

    Normal responses are measured until the response body is finished. SSE is
    intentionally measured only until its response headers are prepared, since
    the stream itself may stay open for hours.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    @staticmethod
    def _display_target(scope: Scope) -> str:
        path = str(scope.get("path", "/"))
        raw_query = scope.get("query_string", b"")
        if not raw_query:
            return path

        try:
            decoded_query = raw_query.decode("utf-8")
        except UnicodeDecodeError:
            return path

        safe_items: list[tuple[str, str]] = []
        for key, value in parse_qsl(decoded_query, keep_blank_values=True):
            safe_value = "***" if key.lower() in _SENSITIVE_QUERY_KEYS else value
            safe_items.append((key, safe_value))

        safe_query = urlencode(safe_items)
        return f"{path}?{safe_query}" if safe_query else path

    @staticmethod
    def _is_sse(message: Message) -> bool:
        if message.get("type") != "http.response.start":
            return False

        for key, value in message.get("headers", []):
            if key.lower() != b"content-type":
                continue
            try:
                content_type = value.decode("latin-1").lower()
            except UnicodeDecodeError:
                return False
            return content_type.startswith("text/event-stream")
        return False

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        # Fast bypass: when disabled there is no clock, query parsing or send
        # wrapper on the request path. This keeps production overhead negligible.
        if not _timing_logs_enabled():
            await self.app(scope, receive, send)
            return

        started_at = time.perf_counter()
        method = str(scope.get("method", "UNKNOWN"))
        target = self._display_target(scope)
        status_code = 500
        is_sse = False
        sse_logged = False

        def elapsed_ms() -> float:
            return (time.perf_counter() - started_at) * 1000.0

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, is_sse, sse_logged

            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 500))
                is_sse = self._is_sse(message)

                if is_sse and not sse_logged:
                    logger.info(
                        "PERF %s %s -> %s | %.1f ms | SSE handshake",
                        method,
                        target,
                        status_code,
                        elapsed_ms(),
                    )
                    sse_logged = True

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            if not is_sse:
                logger.exception(
                    "PERF %s %s -> 500 | %.1f ms | exception",
                    method,
                    target,
                    elapsed_ms(),
                )
            raise
        finally:
            if not is_sse:
                logger.info(
                    "PERF %s %s -> %s | %.1f ms",
                    method,
                    target,
                    status_code,
                    elapsed_ms(),
                )
