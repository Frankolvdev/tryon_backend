from fastapi import (
    APIRouter,
    Depends,
    Header,
    Query,
)
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.auth_guard import (
    auth_guard,
)
from app.models.user import User
from app.repositories.i18n_repository import (
    i18n_repository,
)
from app.schemas.i18n import (
    I18nLocaleListResponse,
    I18nLocaleResponse,
    ResolvedLocaleResponse,
    TranslationDictionaryResponse,
    UserLocalePreferenceResponse,
    UserLocalePreferenceUpdate,
)
from app.services.i18n_dictionary_cache_service import (
    i18n_dictionary_cache_service,
)
from app.services.i18n_service import (
    i18n_service,
)


router = APIRouter()


@router.get(
    "/locales",
    response_model=I18nLocaleListResponse,
)
def list_public_locales(
    db: Session = Depends(get_db),
):
    locales = (
        i18n_repository
        .list_active_locales(db)
    )

    return I18nLocaleListResponse(
        items=[
            I18nLocaleResponse
            .model_validate(locale)
            for locale in locales
        ],
        total=len(locales),
    )


@router.get(
    "/dictionary/{locale_code}",
    response_model=(
        TranslationDictionaryResponse
    ),
)
def get_translation_dictionary(
    locale_code: str,
    db: Session = Depends(get_db),
):
    return (
        i18n_dictionary_cache_service
        .get_dictionary(
            db,
            locale_code=locale_code,
        )
    )


@router.get(
    "/resolved",
    response_model=ResolvedLocaleResponse,
)
def resolve_public_locale(
    locale: str | None = Query(
        default=None,
    ),
    accept_language: str | None = Header(
        default=None,
        alias="Accept-Language",
    ),
    db: Session = Depends(get_db),
):
    return i18n_service.resolved_settings(
        db,
        requested_locale=locale,
        accept_language=accept_language,
    )


@router.get(
    "/me/preferences",
    response_model=(
        UserLocalePreferenceResponse
    ),
)
def get_user_locale_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    preference = (
        i18n_service
        .get_or_create_user_preference(
            db,
            user_id=current_user.id,
        )
    )

    return (
        UserLocalePreferenceResponse
        .model_validate(
            preference
        )
    )


@router.put(
    "/me/preferences",
    response_model=(
        UserLocalePreferenceResponse
    ),
)
def update_user_locale_preferences(
    data: UserLocalePreferenceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    result = (
        i18n_service
        .update_user_preference(
            db,
            user_id=current_user.id,
            data=data,
        )
    )

    return result


@router.get(
    "/me/resolved",
    response_model=ResolvedLocaleResponse,
)
def get_user_resolved_locale(
    locale: str | None = Query(
        default=None,
    ),
    accept_language: str | None = Header(
        default=None,
        alias="Accept-Language",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    return i18n_service.resolved_settings(
        db,
        user_id=current_user.id,
        requested_locale=locale,
        accept_language=accept_language,
    )