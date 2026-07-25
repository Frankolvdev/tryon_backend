import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import (
    RequestValidationError,
)
from fastapi.responses import JSONResponse
from starlette.exceptions import (
    HTTPException as StarletteHTTPException,
)

from app.observability.context import (
    get_correlation_id,
)


logger = logging.getLogger(
    "app.exceptions"
)


def _error_response(
    *,
    status_code: int,
    error_code: str,
    message: str,
    details: Any = None,
) -> JSONResponse:
    correlation_id = (
        get_correlation_id()
    )

    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": {
                "code": error_code,
                "message": message,
                "details": details,
                "correlation_id": (
                    correlation_id
                ),
            },
        },
        headers={
            "X-Correlation-ID": (
                correlation_id or ""
            ),
        },
    )


async def http_exception_handler(
    request: Request,
    exception: StarletteHTTPException,
) -> JSONResponse:
    logger.warning(
        "HTTP exception.",
        extra={
            "event": "http_exception",
            "http_method": request.method,
            "http_path": request.url.path,
            "http_status_code": (
                exception.status_code
            ),
            "exception_detail": (
                exception.detail
            ),
        },
    )

    detail = exception.detail

    if isinstance(detail, str):
        message = detail
        details = None
    else:
        message = "Request failed."
        details = detail

    return _error_response(
        status_code=exception.status_code,
        error_code=(
            f"http_{exception.status_code}"
        ),
        message=message,
        details=details,
    )


async def validation_exception_handler(
    request: Request,
    exception: RequestValidationError,
) -> JSONResponse:
    errors = exception.errors()

    logger.warning(
        "Request validation failed.",
        extra={
            "event": (
                "request_validation_failed"
            ),
            "http_method": request.method,
            "http_path": request.url.path,
            "validation_errors": errors,
        },
    )

    return _error_response(
        status_code=422,
        error_code="validation_error",
        message=(
            "The request contains invalid data."
        ),
        details=errors,
    )


async def unhandled_exception_handler(
    request: Request,
    exception: Exception,
) -> JSONResponse:
    logger.exception(
        "Unhandled application exception.",
        exc_info=(
            type(exception),
            exception,
            exception.__traceback__,
        ),
        extra={
            "event": (
                "unhandled_application_exception"
            ),
            "http_method": request.method,
            "http_path": request.url.path,
            "exception_type": (
                exception.__class__.__name__
            ),
        },
    )

    return _error_response(
        status_code=500,
        error_code="internal_server_error",
        message=(
            "An unexpected internal error "
            "occurred."
        ),
    )


def register_exception_handlers(
    app: FastAPI,
) -> None:
    app.add_exception_handler(
        StarletteHTTPException,
        http_exception_handler,
    )

    app.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,
    )

    app.add_exception_handler(
        Exception,
        unhandled_exception_handler,
    )