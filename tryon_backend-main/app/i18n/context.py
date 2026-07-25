from contextvars import ContextVar, Token
from dataclasses import dataclass

from app.common.i18n_constants import (
    DEFAULT_LOCALE,
)


@dataclass(frozen=True)
class I18nRequestContext:
    locale_code: str = DEFAULT_LOCALE
    fallback_locale_code: str | None = None

    timezone: str = "America/Mexico_City"
    currency_code: str = "MXN"

    date_format: str = "DD/MM/YYYY"
    time_format: str = "HH:mm"

    source: str = "default"


_i18n_context: ContextVar[
    I18nRequestContext
] = ContextVar(
    "i18n_request_context",
    default=I18nRequestContext(),
)


def set_i18n_context(
    *,
    locale_code: str,
    fallback_locale_code: str | None,
    timezone: str,
    currency_code: str,
    date_format: str,
    time_format: str,
    source: str,
) -> Token[I18nRequestContext]:
    context = I18nRequestContext(
        locale_code=locale_code,
        fallback_locale_code=(
            fallback_locale_code
        ),
        timezone=timezone,
        currency_code=currency_code,
        date_format=date_format,
        time_format=time_format,
        source=source,
    )

    return _i18n_context.set(
        context
    )


def reset_i18n_context(
    token: Token[I18nRequestContext],
) -> None:
    _i18n_context.reset(
        token
    )


def clear_i18n_context() -> None:
    _i18n_context.set(
        I18nRequestContext()
    )


def get_i18n_context() -> I18nRequestContext:
    return _i18n_context.get()


def get_current_locale() -> str:
    return (
        get_i18n_context()
        .locale_code
    )


def get_current_timezone() -> str:
    return (
        get_i18n_context()
        .timezone
    )


def get_current_currency_code() -> str:
    return (
        get_i18n_context()
        .currency_code
    )


def get_current_date_format() -> str:
    return (
        get_i18n_context()
        .date_format
    )


def get_current_time_format() -> str:
    return (
        get_i18n_context()
        .time_format
    )