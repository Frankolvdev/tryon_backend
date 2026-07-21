import logging
from collections.abc import Callable
from typing import Any

from jose import JWTError, jwt
from starlette.middleware.base import (
    BaseHTTPMiddleware,
)
from starlette.requests import Request
from starlette.responses import Response

from app.common.i18n_constants import (
    DEFAULT_FALLBACK_LOCALE,
    DEFAULT_LOCALE,
)
from app.core.config import settings
from app.db.database import SessionLocal
from app.i18n.context import (
    reset_i18n_context,
    set_i18n_context,
)
from app.services.i18n_service import (
    i18n_service,
)


logger = logging.getLogger(
    "app.i18n.middleware"
)


class I18nMiddleware(BaseHTTPMiddleware):
    LOCALE_QUERY_PARAMETER = "locale"
    LOCALE_HEADER = "X-Locale"

    def _extract_bearer_token(
        self,
        request: Request,
    ) -> str | None:
        authorization = request.headers.get(
            "authorization"
        )

        if not authorization:
            return None

        scheme, separator, token = (
            authorization.partition(" ")
        )

        if (
            not separator
            or scheme.lower() != "bearer"
            or not token.strip()
        ):
            return None

        return token.strip()

    def _extract_user_id(
        self,
        request: Request,
    ) -> int | None:
        token = self._extract_bearer_token(
            request
        )

        if not token:
            return None

        secret_key = getattr(
            settings,
            "SECRET_KEY",
            None,
        )

        if not secret_key:
            secret_key = getattr(
                settings,
                "JWT_SECRET_KEY",
                None,
            )

        algorithm = getattr(
            settings,
            "ALGORITHM",
            None,
        )

        if not algorithm:
            algorithm = getattr(
                settings,
                "JWT_ALGORITHM",
                "HS256",
            )

        if not secret_key:
            return None

        try:
            payload: dict[str, Any] = (
                jwt.decode(
                    token,
                    secret_key,
                    algorithms=[
                        algorithm
                    ],
                )
            )

        except JWTError:
            return None

        subject = payload.get("sub")

        if subject is None:
            subject = payload.get(
                "user_id"
            )

        if subject is None:
            return None

        try:
            return int(subject)

        except (
            TypeError,
            ValueError,
        ):
            return None

    def _requested_locale(
        self,
        request: Request,
    ) -> tuple[
        str | None,
        str,
    ]:
        query_locale = (
            request.query_params.get(
                self.LOCALE_QUERY_PARAMETER
            )
        )

        if query_locale:
            return (
                query_locale,
                "query",
            )

        header_locale = (
            request.headers.get(
                self.LOCALE_HEADER
            )
        )

        if header_locale:
            return (
                header_locale,
                "x-locale-header",
            )

        return (
            None,
            "automatic",
        )

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        requested_locale, source = (
            self._requested_locale(
                request
            )
        )

        accept_language = (
            request.headers.get(
                "accept-language"
            )
        )

        user_id = self._extract_user_id(
            request
        )

        skip_database_resolution = (
            request.url.path
            == "/api/v1/webhooks/stripe"
        )

        db = None
        context_token = None
        resolved = None

        if not skip_database_resolution:
            db = SessionLocal()

            try:
                resolved = (
                    i18n_service
                    .resolved_settings(
                        db,
                        user_id=user_id,
                        requested_locale=(
                            requested_locale
                        ),
                        accept_language=(
                            accept_language
                        ),
                    )
                )

                if (
                    source == "automatic"
                    and user_id is not None
                ):
                    source = "user-preference"

                elif (
                    source == "automatic"
                    and accept_language
                ):
                    source = (
                        "accept-language"
                    )

                else:
                    source = (
                        source
                        if source
                        != "automatic"
                        else "default"
                    )

            except Exception:
                logger.exception(
                    "Could not resolve request locale.",
                    extra={
                        "requested_locale": (
                            requested_locale
                        ),
                        "user_id": user_id,
                        "path": request.url.path,
                    },
                )

                resolved = None

            finally:
                db.close()

        if resolved is None:
            context_token = (
                set_i18n_context(
                    locale_code=(
                        DEFAULT_LOCALE
                    ),
                    fallback_locale_code=(
                        DEFAULT_FALLBACK_LOCALE
                    ),
                    timezone=(
                        "America/Mexico_City"
                    ),
                    currency_code="MXN",
                    date_format=(
                        "DD/MM/YYYY"
                    ),
                    time_format="HH:mm",
                    source="fallback",
                )
            )

        else:
            context_token = (
                set_i18n_context(
                    locale_code=(
                        resolved.locale_code
                    ),
                    fallback_locale_code=(
                        resolved
                        .fallback_locale_code
                    ),
                    timezone=(
                        resolved.timezone
                    ),
                    currency_code=(
                        resolved.currency_code
                    ),
                    date_format=(
                        resolved.date_format
                    ),
                    time_format=(
                        resolved.time_format
                    ),
                    source=source,
                )
            )

        request.state.locale_code = (
            resolved.locale_code
            if resolved is not None
            else DEFAULT_LOCALE
        )

        request.state.locale_source = source

        try:
            response = await call_next(
                request
            )

            response.headers[
                "Content-Language"
            ] = request.state.locale_code

            response.headers[
                "X-Resolved-Locale"
            ] = request.state.locale_code

            response.headers[
                "X-Locale-Source"
            ] = source

            response.headers[
                "Vary"
            ] = self._merge_vary_header(
                response.headers.get(
                    "Vary"
                )
            )

            return response

        finally:
            if context_token is not None:
                reset_i18n_context(
                    context_token
                )

    def _merge_vary_header(
        self,
        existing_value: str | None,
    ) -> str:
        values = {
            "Accept-Language",
            "X-Locale",
            "Authorization",
        }

        if existing_value:
            values.update(
                item.strip()
                for item
                in existing_value.split(",")
                if item.strip()
            )

        return ", ".join(
            sorted(values)
        )