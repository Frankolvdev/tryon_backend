import re
from uuid import uuid4

from starlette.types import (
    ASGIApp,
    Message,
    Receive,
    Scope,
    Send,
)

from app.observability.context import (
    correlation_id_context,
    request_context,
)


class CorrelationIdMiddleware:
    HEADER_NAME = b"x-correlation-id"
    RESPONSE_HEADER_NAME = b"x-correlation-id"

    MAX_LENGTH = 128

    VALID_PATTERN = re.compile(
        r"^[a-zA-Z0-9._:/-]+$"
    )

    def __init__(
        self,
        app: ASGIApp,
    ):
        self.app = app

    def _header_value(
        self,
        scope: Scope,
    ) -> str | None:
        headers = scope.get(
            "headers",
            [],
        )

        for name, value in headers:
            if name.lower() != self.HEADER_NAME:
                continue

            try:
                return value.decode(
                    "utf-8"
                ).strip()

            except UnicodeDecodeError:
                return None

        return None

    def _valid_or_new(
        self,
        candidate: str | None,
    ) -> str:
        if (
            candidate
            and len(candidate)
            <= self.MAX_LENGTH
            and self.VALID_PATTERN.fullmatch(
                candidate
            )
        ):
            return candidate

        return uuid4().hex

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

        correlation_id = self._valid_or_new(
            self._header_value(scope)
        )

        correlation_token = (
            correlation_id_context.set(
                correlation_id
            )
        )

        request_token = request_context.set(
            {}
        )

        async def send_wrapper(
            message: Message,
        ) -> None:
            if (
                message["type"]
                == "http.response.start"
            ):
                headers = list(
                    message.get(
                        "headers",
                        [],
                    )
                )

                headers.append(
                    (
                        self.RESPONSE_HEADER_NAME,
                        correlation_id.encode(
                            "utf-8"
                        ),
                    )
                )

                message["headers"] = headers

            await send(message)

        try:
            await self.app(
                scope,
                receive,
                send_wrapper,
            )

        finally:
            correlation_id_context.reset(
                correlation_token
            )

            request_context.reset(
                request_token
            )