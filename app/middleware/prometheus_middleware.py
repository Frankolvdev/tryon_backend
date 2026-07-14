import time

from starlette.types import (
    ASGIApp,
    Message,
    Receive,
    Scope,
    Send,
)

from app.observability.metrics import (
    HTTP_EXCEPTIONS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_IN_PROGRESS,
    HTTP_REQUESTS_TOTAL,
    HTTP_RESPONSE_SIZE_BYTES,
)


class PrometheusMiddleware:
    EXCLUDED_PATHS = {
        "/metrics",
        "/favicon.ico",
    }

    def __init__(
        self,
        app: ASGIApp,
    ):
        self.app = app

    def _route_name(
        self,
        scope: Scope,
    ) -> str:
        route = scope.get("route")

        if route is not None:
            route_path = getattr(
                route,
                "path",
                None,
            )

            if route_path:
                return str(route_path)

        return str(
            scope.get(
                "path",
                "unknown",
            )
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

        path = str(
            scope.get(
                "path",
                "unknown",
            )
        )

        if path in self.EXCLUDED_PATHS:
            await self.app(
                scope,
                receive,
                send,
            )
            return

        method = str(
            scope.get(
                "method",
                "UNKNOWN",
            )
        )

        started_at = time.perf_counter()
        status_code = 500
        response_size = 0

        initial_route = self._route_name(
            scope
        )

        HTTP_REQUESTS_IN_PROGRESS.labels(
            method=method,
            route=initial_route,
        ).inc()

        async def send_wrapper(
            message: Message,
        ) -> None:
            nonlocal status_code
            nonlocal response_size

            if (
                message["type"]
                == "http.response.start"
            ):
                status_code = int(
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
                        response_size = int(
                            value.decode(
                                "ascii"
                            )
                        )
                    except (
                        ValueError,
                        UnicodeDecodeError,
                    ):
                        response_size = 0

            elif (
                message["type"]
                == "http.response.body"
                and response_size <= 0
            ):
                body = message.get(
                    "body",
                    b"",
                )

                response_size += len(body)

            await send(message)

        try:
            await self.app(
                scope,
                receive,
                send_wrapper,
            )

        except Exception as error:
            final_route = self._route_name(
                scope
            )

            HTTP_EXCEPTIONS_TOTAL.labels(
                method=method,
                route=final_route,
                exception_type=(
                    error.__class__.__name__
                ),
            ).inc()

            raise

        finally:
            duration_seconds = (
                time.perf_counter()
                - started_at
            )

            final_route = self._route_name(
                scope
            )

            HTTP_REQUESTS_IN_PROGRESS.labels(
                method=method,
                route=initial_route,
            ).dec()

            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                route=final_route,
                status_code=str(
                    status_code
                ),
            ).inc()

            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method,
                route=final_route,
            ).observe(
                duration_seconds
            )

            HTTP_RESPONSE_SIZE_BYTES.labels(
                method=method,
                route=final_route,
                status_code=str(
                    status_code
                ),
            ).observe(
                max(
                    response_size,
                    0,
                )
            )