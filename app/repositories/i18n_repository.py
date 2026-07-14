from sqlalchemy import (
    func,
    or_,
    select,
)
from sqlalchemy.orm import Session

from app.models.i18n_locale import I18nLocale
from app.models.i18n_translation import (
    I18nTranslation,
)
from app.models.user_locale_preference import (
    UserLocalePreference,
)


class I18nRepository:
    def get_locale(
        self,
        db: Session,
        *,
        locale_code: str,
    ) -> I18nLocale | None:
        return db.get(
            I18nLocale,
            locale_code,
        )

    def get_default_locale(
        self,
        db: Session,
    ) -> I18nLocale | None:
        statement = (
            select(I18nLocale)
            .where(
                I18nLocale.is_default.is_(True),
                I18nLocale.is_active.is_(True),
            )
            .limit(1)
        )

        return db.execute(
            statement
        ).scalar_one_or_none()

    def list_locales(
        self,
        db: Session,
        *,
        active_only: bool = False,
    ) -> list[I18nLocale]:
        statement = select(
            I18nLocale
        )

        if active_only:
            statement = statement.where(
                I18nLocale.is_active.is_(True)
            )

        statement = statement.order_by(
            I18nLocale.is_default.desc(),
            I18nLocale.code.asc(),
        )

        return list(
            db.execute(
                statement
            ).scalars().all()
        )

    def list_active_locales(
        self,
        db: Session,
    ) -> list[I18nLocale]:
        return self.list_locales(
            db,
            active_only=True,
        )

    def get_translation(
        self,
        db: Session,
        *,
        locale_code: str,
        translation_key: str,
        active_only: bool = True,
    ) -> I18nTranslation | None:
        statement = select(
            I18nTranslation
        ).where(
            I18nTranslation.locale_code
            == locale_code,
            I18nTranslation.translation_key
            == translation_key,
        )

        if active_only:
            statement = statement.where(
                I18nTranslation.is_active.is_(
                    True
                )
            )

        return db.execute(
            statement
        ).scalar_one_or_none()

    def get_translation_by_id(
        self,
        db: Session,
        *,
        translation_id: int,
    ) -> I18nTranslation | None:
        return db.get(
            I18nTranslation,
            translation_id,
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
    ) -> list[I18nTranslation]:
        statement = select(
            I18nTranslation
        )

        if locale_code:
            statement = statement.where(
                I18nTranslation.locale_code
                == locale_code
            )

        if namespace:
            statement = statement.where(
                I18nTranslation.namespace
                == namespace
            )

        if is_active is not None:
            statement = statement.where(
                I18nTranslation.is_active.is_(
                    is_active
                )
            )

        if search:
            pattern = (
                f"%{search.strip()}%"
            )

            statement = statement.where(
                or_(
                    I18nTranslation.translation_key.ilike(
                        pattern
                    ),
                    I18nTranslation.value.ilike(
                        pattern
                    ),
                    I18nTranslation.description.ilike(
                        pattern
                    ),
                )
            )

        statement = (
            statement
            .order_by(
                I18nTranslation.locale_code.asc(),
                I18nTranslation.translation_key.asc(),
            )
            .offset(skip)
            .limit(limit)
        )

        return list(
            db.execute(
                statement
            ).scalars().all()
        )

    def count_translations(
        self,
        db: Session,
        *,
        locale_code: str | None = None,
        namespace: str | None = None,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> int:
        statement = select(
            func.count(
                I18nTranslation.id
            )
        )

        if locale_code:
            statement = statement.where(
                I18nTranslation.locale_code
                == locale_code
            )

        if namespace:
            statement = statement.where(
                I18nTranslation.namespace
                == namespace
            )

        if is_active is not None:
            statement = statement.where(
                I18nTranslation.is_active.is_(
                    is_active
                )
            )

        if search:
            pattern = (
                f"%{search.strip()}%"
            )

            statement = statement.where(
                or_(
                    I18nTranslation.translation_key.ilike(
                        pattern
                    ),
                    I18nTranslation.value.ilike(
                        pattern
                    ),
                    I18nTranslation.description.ilike(
                        pattern
                    ),
                )
            )

        return int(
            db.execute(
                statement
            ).scalar_one()
        )

    def get_user_preference(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> UserLocalePreference | None:
        statement = select(
            UserLocalePreference
        ).where(
            UserLocalePreference.user_id
            == user_id
        )

        return db.execute(
            statement
        ).scalar_one_or_none()


i18n_repository = I18nRepository()