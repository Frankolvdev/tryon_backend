from string import Formatter
from typing import Any
from zoneinfo import (
    ZoneInfo,
    ZoneInfoNotFoundError,
)

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.exceptions import (
    ConflictException,
    NotFoundException,
)
from app.common.i18n_constants import (
    DEFAULT_FALLBACK_LOCALE,
    DEFAULT_LOCALE,
    DEFAULT_TRANSLATIONS,
    SUPPORTED_INITIAL_LOCALES,
)
from app.models.i18n_locale import I18nLocale
from app.models.i18n_translation import (
    I18nTranslation,
)
from app.models.user_locale_preference import (
    UserLocalePreference,
)
from app.repositories.i18n_repository import (
    i18n_repository,
)
from app.schemas.i18n import (
    ResolvedLocaleResponse,
    TranslationDictionaryResponse,
    UserLocalePreferenceResponse,
    UserLocalePreferenceUpdate,
)


class I18nService:
    def normalize_locale_code(
        self,
        locale_code: str | None,
    ) -> str:
        if not locale_code:
            return DEFAULT_LOCALE

        value = (
            locale_code.strip()
            .replace("_", "-")
        )

        parts = value.split("-")

        if len(parts) == 1:
            return parts[0].lower()

        return (
            parts[0].lower()
            + "-"
            + parts[1].upper()
        )

    def namespace_from_key(
        self,
        translation_key: str,
    ) -> str:
        if "." not in translation_key:
            return "common"

        return translation_key.split(
            ".",
            1,
        )[0]

    def validate_timezone(
        self,
        timezone_name: str,
    ) -> str:
        try:
            ZoneInfo(timezone_name)

        except ZoneInfoNotFoundError as error:
            raise ConflictException(
                "Invalid IANA timezone."
            ) from error

        return timezone_name

    def ensure_initial_data(
        self,
        db: Session,
    ) -> None:
        for locale_code, config in (
            SUPPORTED_INITIAL_LOCALES.items()
        ):
            locale = db.get(
                I18nLocale,
                locale_code,
            )

            if locale is None:
                locale = I18nLocale(
                    code=locale_code,
                    name=config["name"],
                    native_name=(
                        config["native_name"]
                    ),
                    fallback_locale_code=(
                        DEFAULT_FALLBACK_LOCALE
                        if locale_code
                        != DEFAULT_FALLBACK_LOCALE
                        else None
                    ),
                    currency_code=(
                        config["currency_code"]
                    ),
                    timezone=config["timezone"],
                    date_format=(
                        config["date_format"]
                    ),
                    time_format=(
                        config["time_format"]
                    ),
                    is_active=True,
                    is_default=(
                        locale_code
                        == DEFAULT_LOCALE
                    ),
                )

                db.add(locale)

        db.flush()

        for locale_code, translations in (
            DEFAULT_TRANSLATIONS.items()
        ):
            for key, value in translations.items():
                existing = db.execute(
                    select(
                        I18nTranslation
                    ).where(
                        I18nTranslation.locale_code
                        == locale_code,
                        I18nTranslation.translation_key
                        == key,
                    )
                ).scalar_one_or_none()

                if existing is not None:
                    continue

                db.add(
                    I18nTranslation(
                        locale_code=locale_code,
                        namespace=(
                            self.namespace_from_key(
                                key
                            )
                        ),
                        translation_key=key,
                        value=value,
                        is_active=True,
                        is_html=False,
                    )
                )

        db.commit()

    def resolve_locale(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        requested_locale: str | None = None,
        accept_language: str | None = None,
    ) -> I18nLocale:
        candidates: list[str] = []

        if requested_locale:
            candidates.append(
                self.normalize_locale_code(
                    requested_locale
                )
            )

        if user_id is not None:
            preference = (
                i18n_repository
                .get_user_preference(
                    db,
                    user_id=user_id,
                )
            )

            if preference is not None:
                candidates.append(
                    preference.locale_code
                )

        if accept_language:
            for item in accept_language.split(","):
                raw_code = (
                    item.split(
                        ";",
                        1,
                    )[0]
                    .strip()
                )

                if raw_code:
                    candidates.append(
                        self.normalize_locale_code(
                            raw_code
                        )
                    )

        candidates.extend(
            [
                DEFAULT_LOCALE,
                DEFAULT_FALLBACK_LOCALE,
            ]
        )

        checked: set[str] = set()

        for candidate in candidates:
            if candidate in checked:
                continue

            checked.add(candidate)

            locale = (
                i18n_repository.get_locale(
                    db,
                    locale_code=candidate,
                )
            )

            if (
                locale is not None
                and locale.is_active
            ):
                return locale

            language_code = candidate.split(
                "-",
                1,
            )[0]

            active_locales = (
                i18n_repository
                .list_active_locales(db)
            )

            for active_locale in active_locales:
                if (
                    active_locale.code.split(
                        "-",
                        1,
                    )[0]
                    == language_code
                ):
                    return active_locale

        default_locale = (
            i18n_repository
            .get_default_locale(db)
        )

        if default_locale is None:
            raise NotFoundException(
                "No active locale is configured."
            )

        return default_locale

    def resolved_settings(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        requested_locale: str | None = None,
        accept_language: str | None = None,
    ) -> ResolvedLocaleResponse:
        locale = self.resolve_locale(
            db,
            user_id=user_id,
            requested_locale=requested_locale,
            accept_language=accept_language,
        )

        preference = None

        if user_id is not None:
            preference = (
                i18n_repository
                .get_user_preference(
                    db,
                    user_id=user_id,
                )
            )

        return ResolvedLocaleResponse(
            locale_code=locale.code,
            fallback_locale_code=(
                locale.fallback_locale_code
            ),
            timezone=(
                preference.timezone
                if (
                    preference is not None
                    and preference.timezone
                )
                else locale.timezone
            ),
            currency_code=(
                preference.currency_code
                if (
                    preference is not None
                    and preference.currency_code
                )
                else locale.currency_code
            ),
            date_format=(
                preference.date_format
                if (
                    preference is not None
                    and preference.date_format
                )
                else locale.date_format
            ),
            time_format=(
                preference.time_format
                if (
                    preference is not None
                    and preference.time_format
                )
                else locale.time_format
            ),
        )

    def translate(
        self,
        db: Session,
        *,
        translation_key: str,
        locale_code: str | None = None,
        user_id: int | None = None,
        variables: dict[str, Any] | None = None,
        default: str | None = None,
    ) -> str:
        locale = self.resolve_locale(
            db,
            user_id=user_id,
            requested_locale=locale_code,
        )

        translation = (
            i18n_repository
            .get_translation(
                db,
                locale_code=locale.code,
                translation_key=(
                    translation_key
                ),
            )
        )

        if (
            translation is None
            and locale.fallback_locale_code
        ):
            translation = (
                i18n_repository
                .get_translation(
                    db,
                    locale_code=(
                        locale
                        .fallback_locale_code
                    ),
                    translation_key=(
                        translation_key
                    ),
                )
            )

        text = (
            translation.value
            if translation is not None
            else (
                default
                or translation_key
            )
        )

        if not variables:
            return text

        allowed_fields = {
            field_name
            for _, field_name, _, _
            in Formatter().parse(text)
            if field_name
        }

        safe_variables = {
            key: value
            for key, value in variables.items()
            if key in allowed_fields
        }

        try:
            return text.format(
                **safe_variables
            )

        except (
            KeyError,
            ValueError,
            IndexError,
        ):
            return text

    def dictionary(
        self,
        db: Session,
        *,
        locale_code: str,
    ) -> TranslationDictionaryResponse:
        locale = self.resolve_locale(
            db,
            requested_locale=locale_code,
        )

        translations: dict[str, str] = {}

        if locale.fallback_locale_code:
            fallback_items = (
                i18n_repository
                .list_translations(
                    db,
                    locale_code=(
                        locale
                        .fallback_locale_code
                    ),
                )
            )

            translations.update(
                {
                    item.translation_key: (
                        item.value
                    )
                    for item in fallback_items
                }
            )

        locale_items = (
            i18n_repository
            .list_translations(
                db,
                locale_code=locale.code,
            )
        )

        translations.update(
            {
                item.translation_key: (
                    item.value
                )
                for item in locale_items
            }
        )

        return TranslationDictionaryResponse(
            locale_code=locale.code,
            translations=translations,
        )

    def get_or_create_user_preference(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> UserLocalePreference:
        preference = (
            i18n_repository
            .get_user_preference(
                db,
                user_id=user_id,
            )
        )

        if preference is not None:
            return preference

        locale = self.resolve_locale(
            db,
        )

        preference = UserLocalePreference(
            user_id=user_id,
            locale_code=locale.code,
            timezone=locale.timezone,
            currency_code=(
                locale.currency_code
            ),
            date_format=locale.date_format,
            time_format=locale.time_format,
        )

        db.add(preference)
        db.commit()
        db.refresh(preference)

        return preference

    def update_user_preference(
        self,
        db: Session,
        *,
        user_id: int,
        data: UserLocalePreferenceUpdate,
    ) -> UserLocalePreferenceResponse:
        locale_code = (
            self.normalize_locale_code(
                data.locale_code
            )
        )

        locale = (
            i18n_repository.get_locale(
                db,
                locale_code=locale_code,
            )
        )

        if (
            locale is None
            or not locale.is_active
        ):
            raise ConflictException(
                "The selected locale is not available."
            )

        preference = (
            self.get_or_create_user_preference(
                db,
                user_id=user_id,
            )
        )

        preference.locale_code = (
            locale.code
        )

        preference.timezone = (
            self.validate_timezone(
                data.timezone
            )
            if data.timezone
            else locale.timezone
        )

        preference.currency_code = (
            data.currency_code.upper()
            if data.currency_code
            else locale.currency_code
        )

        preference.date_format = (
            data.date_format
            or locale.date_format
        )

        preference.time_format = (
            data.time_format
            or locale.time_format
        )

        db.add(preference)
        db.commit()
        db.refresh(preference)

        return UserLocalePreferenceResponse.model_validate(
            preference
        )


i18n_service = I18nService()