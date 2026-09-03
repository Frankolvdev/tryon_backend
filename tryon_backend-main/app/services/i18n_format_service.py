from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.i18n.context import (
    get_current_currency_code,
    get_current_locale,
    get_current_timezone,
)
from app.services.i18n_service import i18n_service


class I18nFormatService:
    CURRENCY_SYMBOLS = {
        "MXN": "$",
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "JPY": "¥",
        "CAD": "$",
        "AUD": "$",
    }

    def _resolve_settings(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        locale_code: str | None = None,
    ):
        return i18n_service.resolved_settings(
            db,
            user_id=user_id,
            requested_locale=(
                locale_code
                or get_current_locale()
            ),
        )

    def _timezone(
        self,
        timezone_name: str,
    ) -> ZoneInfo:
        try:
            return ZoneInfo(
                timezone_name
            )

        except ZoneInfoNotFoundError:
            return ZoneInfo("UTC")

    def localize_datetime(
        self,
        value: datetime,
        *,
        timezone_name: str | None = None,
    ) -> datetime:
        resolved_timezone = (
            timezone_name
            or get_current_timezone()
            or "UTC"
        )

        if value.tzinfo is None:
            value = value.replace(
                tzinfo=timezone.utc
            )

        return value.astimezone(
            self._timezone(
                resolved_timezone
            )
        )

    def format_datetime(
        self,
        db: Session,
        *,
        value: datetime,
        user_id: int | None = None,
        locale_code: str | None = None,
        timezone_name: str | None = None,
        include_time: bool = True,
    ) -> str:
        settings = self._resolve_settings(
            db,
            user_id=user_id,
            locale_code=locale_code,
        )

        localized = self.localize_datetime(
            value,
            timezone_name=(
                timezone_name
                or settings.timezone
            ),
        )

        locale = settings.locale_code

        if locale.startswith("en"):
            date_value = localized.strftime(
                "%m/%d/%Y"
            )

            time_value = localized.strftime(
                "%I:%M %p"
            ).lstrip("0")

        else:
            date_value = localized.strftime(
                "%d/%m/%Y"
            )

            time_value = localized.strftime(
                "%H:%M"
            )

        if include_time:
            return (
                f"{date_value} {time_value}"
            )

        return date_value

    def format_date(
        self,
        db: Session,
        *,
        value: date | datetime,
        user_id: int | None = None,
        locale_code: str | None = None,
    ) -> str:
        if isinstance(value, datetime):
            return self.format_datetime(
                db,
                value=value,
                user_id=user_id,
                locale_code=locale_code,
                include_time=False,
            )

        locale = (
            locale_code
            or get_current_locale()
        )

        if locale.startswith("en"):
            return value.strftime(
                "%m/%d/%Y"
            )

        return value.strftime(
            "%d/%m/%Y"
        )

    def format_currency(
        self,
        value: int | float | Decimal | str,
        *,
        currency_code: str | None = None,
        locale_code: str | None = None,
        decimals: int = 2,
    ) -> str:
        resolved_currency = (
            currency_code
            or get_current_currency_code()
            or "MXN"
        ).upper()

        resolved_locale = (
            locale_code
            or get_current_locale()
        )

        try:
            amount = Decimal(
                str(value)
            )

        except (
            InvalidOperation,
            ValueError,
            TypeError,
        ):
            amount = Decimal("0")

        formatted = (
            f"{amount:,.{decimals}f}"
        )

        if resolved_locale.startswith(
            "es"
        ):
            formatted = (
                formatted
                .replace(",", "_")
                .replace(".", ",")
                .replace("_", ".")
            )

        symbol = self.CURRENCY_SYMBOLS.get(
            resolved_currency,
            resolved_currency,
        )

        if resolved_currency in {
            "MXN",
            "USD",
            "CAD",
            "AUD",
        }:
            return (
                f"{symbol}{formatted} "
                f"{resolved_currency}"
            )

        return (
            f"{symbol}{formatted}"
        )


i18n_format_service = (
    I18nFormatService()
)