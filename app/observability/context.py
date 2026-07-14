from contextvars import ContextVar, Token
from typing import Any


correlation_id_context: ContextVar[str | None] = (
    ContextVar(
        "correlation_id",
        default=None,
    )
)

request_context: ContextVar[
    dict[str, Any]
] = ContextVar(
    "request_context",
    default={},
)


def get_correlation_id() -> str | None:
    return correlation_id_context.get()


def set_correlation_id(
    correlation_id: str,
) -> Token:
    return correlation_id_context.set(
        correlation_id
    )


def get_request_context() -> dict[str, Any]:
    return dict(
        request_context.get()
    )


def set_request_context(
    value: dict[str, Any],
) -> Token:
    return request_context.set(
        dict(value)
    )


def update_request_context(
    **values: Any,
) -> None:
    current = get_request_context()
    current.update(values)

    request_context.set(current)


def clear_observability_context() -> None:
    correlation_id_context.set(None)
    request_context.set({})