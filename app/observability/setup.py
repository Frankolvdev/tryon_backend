from fastapi import FastAPI

from app.middleware.correlation_id_middleware import (
    CorrelationIdMiddleware,
)
from app.middleware.request_logging_middleware import (
    RequestLoggingMiddleware,
)
from app.observability.exception_handlers import (
    register_exception_handlers,
)
from app.observability.logging_config import (
    configure_logging,
)


def setup_observability(
    app: FastAPI,
) -> None:
    configure_logging()

    register_exception_handlers(app)

    app.add_middleware(
        RequestLoggingMiddleware
    )

    app.add_middleware(
        CorrelationIdMiddleware
    )