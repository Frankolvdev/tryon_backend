from fastapi import Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.i18n.context import (
    get_current_locale,
)
from app.services.i18n_service import (
    i18n_service,
)


class RequestTranslator:
    def __init__(
        self,
        db: Session,
        locale_code: str,
    ):
        self.db = db
        self.locale_code = locale_code

    def translate(
        self,
        translation_key: str,
        *,
        variables: dict | None = None,
        default: str | None = None,
    ) -> str:
        return i18n_service.translate(
            self.db,
            translation_key=(
                translation_key
            ),
            locale_code=(
                self.locale_code
            ),
            variables=variables,
            default=default,
        )

    def __call__(
        self,
        translation_key: str,
        *,
        variables: dict | None = None,
        default: str | None = None,
    ) -> str:
        return self.translate(
            translation_key,
            variables=variables,
            default=default,
        )


def get_request_translator(
    db: Session = Depends(get_db),
) -> RequestTranslator:
    return RequestTranslator(
        db=db,
        locale_code=(
            get_current_locale()
        ),
    )