from typing import Any

from sqlalchemy.orm import Session

from app.common.i18n_constants import (
    DEFAULT_LOCALE,
)
from app.i18n.context import (
    get_current_locale,
)
from app.services.i18n_service import (
    i18n_service,
)


class LocalizedMessageService:
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
        resolved_locale = (
            locale_code
            or get_current_locale()
            or DEFAULT_LOCALE
        )

        return i18n_service.translate(
            db,
            translation_key=(
                translation_key
            ),
            locale_code=(
                resolved_locale
            ),
            user_id=user_id,
            variables=variables,
            default=default,
        )

    def for_user(
        self,
        db: Session,
        *,
        user_id: int,
        translation_key: str,
        variables: dict[str, Any] | None = None,
        default: str | None = None,
    ) -> str:
        return i18n_service.translate(
            db,
            translation_key=(
                translation_key
            ),
            user_id=user_id,
            variables=variables,
            default=default,
        )


localized_message_service = (
    LocalizedMessageService()
)