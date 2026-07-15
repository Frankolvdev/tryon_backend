from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from app.common.exceptions import AppException
from app.common.i18n_constants import DEFAULT_LOCALE
from app.common.localized_exceptions import (
    LocalizedApplicationException,
)
from app.db.database import SessionLocal
from app.i18n.context import get_current_locale
from app.services.i18n_service import i18n_service


logger = logging.getLogger("app.exception_handlers")


async def app_exception_handler(
    request: Request,
    exception: AppException,
) -> JSONResponse:
    return JSONResponse(
        status_code=exception.status_code,
        content={
            "success": False,
            "detail": exception.message,
            "error": {
                "code": exception.error_code,
                "message": exception.message,
            },
        },
    )


async def localized_exception_handler(
    request: Request,
    exception: LocalizedApplicationException,
) -> JSONResponse:
    locale_code = getattr(
        request.state,
        "locale_code",
        None,
    )

    if not locale_code:
        locale_code = (
            get_current_locale()
            or DEFAULT_LOCALE
        )

    db = SessionLocal()

    try:
        message = i18n_service.translate(
            db,
            translation_key=exception.translation_key,
            locale_code=locale_code,
            variables=exception.variables,
            default=exception.default_message,
        )
    except Exception:
        logger.exception(
            "Could not translate application exception.",
            extra={
                "translation_key": exception.translation_key,
                "locale_code": locale_code,
            },
        )

        message = exception.default_message
    finally:
        db.close()

    return JSONResponse(
        status_code=exception.status_code,
        content={
            "success": False,
            "detail": message,
            "error": {
                "code": exception.error_code,
                "message": message,
                "translation_key": exception.translation_key,
                "locale": locale_code,
            },
        },
        headers={
            "Content-Language": locale_code,
        },
    )