from zoneinfo import (
    ZoneInfo,
    ZoneInfoNotFoundError,
)

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.common.exceptions import (
    ConflictException,
    NotFoundException,
)
from app.common.i18n_constants import (
    DEFAULT_TRANSLATIONS,
    SUPPORTED_INITIAL_LOCALES,
)
from app.models.i18n_locale import I18nLocale
from app.models.i18n_translation import (
    I18nTranslation,
)
from app.repositories.i18n_repository import (
    i18n_repository,
)
from app.schemas.i18n import (
    I18nLocaleCreate,
    I18nLocaleListResponse,
    I18nLocaleResponse,
    I18nLocaleUpdate,
    I18nSeedResponse,
    I18nTranslationCreate,
    I18nTranslationListResponse,
    I18nTranslationResponse,
    I18nTranslationUpdate,
)
from app.services.i18n_service import (
    i18n_service,
)


class I18nAdminService:
    def _validate_timezone(
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

    def _validate_fallback(
        self,
        db: Session,
        *,
        locale_code: str,
        fallback_locale_code: str | None,
    ) -> None:
        if fallback_locale_code is None:
            return

        if locale_code == fallback_locale_code:
            raise ConflictException(
                "A locale cannot use itself as fallback."
            )

        fallback = (
            i18n_repository.get_locale(
                db,
                locale_code=(
                    fallback_locale_code
                ),
            )
        )

        if fallback is None:
            raise ConflictException(
                "Fallback locale does not exist."
            )

    def _unset_other_defaults(
        self,
        db: Session,
        *,
        locale_code: str,
    ) -> None:
        db.execute(
            update(I18nLocale)
            .where(
                I18nLocale.code
                != locale_code
            )
            .values(
                is_default=False
            )
        )

    def list_locales(
        self,
        db: Session,
        *,
        active_only: bool = False,
    ) -> I18nLocaleListResponse:
        items = (
            i18n_repository.list_locales(
                db,
                active_only=active_only,
            )
        )

        return I18nLocaleListResponse(
            items=[
                I18nLocaleResponse.model_validate(
                    item
                )
                for item in items
            ],
            total=len(items),
        )

    def create_locale(
        self,
        db: Session,
        *,
        data: I18nLocaleCreate,
    ) -> I18nLocaleResponse:
        existing = (
            i18n_repository.get_locale(
                db,
                locale_code=data.code,
            )
        )

        if existing is not None:
            raise ConflictException(
                "Locale already exists."
            )

        self._validate_timezone(
            data.timezone
        )

        self._validate_fallback(
            db,
            locale_code=data.code,
            fallback_locale_code=(
                data.fallback_locale_code
            ),
        )

        if data.is_default:
            self._unset_other_defaults(
                db,
                locale_code=data.code,
            )

        locale = I18nLocale(
            code=data.code,
            name=data.name,
            native_name=data.native_name,
            fallback_locale_code=(
                data.fallback_locale_code
            ),
            currency_code=(
                data.currency_code
            ),
            timezone=data.timezone,
            date_format=data.date_format,
            time_format=data.time_format,
            is_active=data.is_active,
            is_default=data.is_default,
        )

        db.add(locale)
        db.commit()
        db.refresh(locale)

        return I18nLocaleResponse.model_validate(
            locale
        )

    def update_locale(
        self,
        db: Session,
        *,
        locale_code: str,
        data: I18nLocaleUpdate,
    ) -> I18nLocaleResponse:
        normalized_code = (
            i18n_service
            .normalize_locale_code(
                locale_code
            )
        )

        locale = (
            i18n_repository.get_locale(
                db,
                locale_code=normalized_code,
            )
        )

        if locale is None:
            raise NotFoundException(
                "Locale not found."
            )

        update_data = data.model_dump(
            exclude_unset=True
        )

        if (
            "timezone" in update_data
            and update_data["timezone"]
            is not None
        ):
            self._validate_timezone(
                update_data["timezone"]
            )

        if (
            "fallback_locale_code"
            in update_data
        ):
            self._validate_fallback(
                db,
                locale_code=locale.code,
                fallback_locale_code=(
                    update_data[
                        "fallback_locale_code"
                    ]
                ),
            )

        if update_data.get(
            "is_default"
        ) is True:
            self._unset_other_defaults(
                db,
                locale_code=locale.code,
            )

            locale.is_active = True

        if (
            update_data.get(
                "is_active"
            )
            is False
            and locale.is_default
        ):
            raise ConflictException(
                "The default locale cannot be disabled."
            )

        for field, value in (
            update_data.items()
        ):
            setattr(
                locale,
                field,
                value,
            )

        db.add(locale)
        db.commit()
        db.refresh(locale)

        return I18nLocaleResponse.model_validate(
            locale
        )

    def list_translations(
        self,
        db: Session,
        *,
        locale_code: str | None = None,
        namespace: str | None = None,
        search: str | None = None,
        is_active: bool | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> I18nTranslationListResponse:
        normalized_locale = (
            i18n_service
            .normalize_locale_code(
                locale_code
            )
            if locale_code
            else None
        )

        items = (
            i18n_repository
            .list_translations(
                db,
                locale_code=(
                    normalized_locale
                ),
                namespace=namespace,
                search=search,
                is_active=is_active,
                skip=skip,
                limit=limit,
            )
        )

        total = (
            i18n_repository
            .count_translations(
                db,
                locale_code=(
                    normalized_locale
                ),
                namespace=namespace,
                search=search,
                is_active=is_active,
            )
        )

        return I18nTranslationListResponse(
            items=[
                I18nTranslationResponse
                .model_validate(item)
                for item in items
            ],
            total=total,
            skip=skip,
            limit=limit,
        )

    def create_translation(
        self,
        db: Session,
        *,
        data: I18nTranslationCreate,
    ) -> I18nTranslationResponse:
        locale = (
            i18n_repository.get_locale(
                db,
                locale_code=(
                    data.locale_code
                ),
            )
        )

        if locale is None:
            raise NotFoundException(
                "Locale not found."
            )

        existing = (
            i18n_repository
            .get_translation(
                db,
                locale_code=(
                    data.locale_code
                ),
                translation_key=(
                    data.translation_key
                ),
                active_only=False,
            )
        )

        if existing is not None:
            raise ConflictException(
                "Translation key already exists "
                "for this locale."
            )

        translation = I18nTranslation(
            locale_code=(
                data.locale_code
            ),
            namespace=(
                i18n_service
                .namespace_from_key(
                    data.translation_key
                )
            ),
            translation_key=(
                data.translation_key
            ),
            value=data.value,
            description=data.description,
            is_html=data.is_html,
            is_active=data.is_active,
        )

        db.add(translation)
        db.commit()
        db.refresh(translation)

        return (
            I18nTranslationResponse
            .model_validate(
                translation
            )
        )

    def update_translation(
        self,
        db: Session,
        *,
        translation_id: int,
        data: I18nTranslationUpdate,
    ) -> I18nTranslationResponse:
        translation = (
            i18n_repository
            .get_translation_by_id(
                db,
                translation_id=(
                    translation_id
                ),
            )
        )

        if translation is None:
            raise NotFoundException(
                "Translation not found."
            )

        update_data = data.model_dump(
            exclude_unset=True
        )

        for field, value in (
            update_data.items()
        ):
            setattr(
                translation,
                field,
                value,
            )

        db.add(translation)
        db.commit()
        db.refresh(translation)

        return (
            I18nTranslationResponse
            .model_validate(
                translation
            )
        )

    def seed_initial_data(
        self,
        db: Session,
    ) -> I18nSeedResponse:
        i18n_service.ensure_initial_data(
            db
        )

        translations_processed = sum(
            len(items)
            for items
            in DEFAULT_TRANSLATIONS.values()
        )

        return I18nSeedResponse(
            success=True,
            locales_processed=len(
                SUPPORTED_INITIAL_LOCALES
            ),
            translations_processed=(
                translations_processed
            ),
            message=(
                "Initial locales and translations "
                "were processed successfully."
            ),
        )


i18n_admin_service = (
    I18nAdminService()
)