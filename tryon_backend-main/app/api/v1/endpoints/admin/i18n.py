from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
    status,
)
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import (
    admin_guard,
)
from app.models.user import User
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
from app.services.audit_entry_service import (
    audit_entry_service,
)
from app.services.i18n_admin_service import (
    i18n_admin_service,
)


router = APIRouter()


@router.get(
    "/i18n/locales",
    response_model=I18nLocaleListResponse,
)
def list_admin_locales(
    active_only: bool = Query(
        default=False,
    ),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    return i18n_admin_service.list_locales(
        db,
        active_only=active_only,
    )


@router.post(
    "/i18n/locales",
    response_model=I18nLocaleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_locale(
    data: I18nLocaleCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    result = (
        i18n_admin_service
        .create_locale(
            db,
            data=data,
        )
    )

    audit_entry_service.safe_record(
        db,
        action="create",
        entity_type="i18n_locale",
        entity_id=result.code,
        actor=current_admin,
        before=None,
        after=result,
        request=request,
        metadata={
            "module": "i18n",
        },
    )

    return result


@router.put(
    "/i18n/locales/{locale_code}",
    response_model=I18nLocaleResponse,
)
def update_locale(
    locale_code: str,
    data: I18nLocaleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    before_list = (
        i18n_admin_service
        .list_locales(
            db,
            active_only=False,
        )
    )

    before = next(
        (
            item
            for item
            in before_list.items
            if item.code == locale_code
        ),
        None,
    )

    result = (
        i18n_admin_service
        .update_locale(
            db,
            locale_code=locale_code,
            data=data,
        )
    )

    audit_entry_service.safe_record(
        db,
        action="update",
        entity_type="i18n_locale",
        entity_id=result.code,
        actor=current_admin,
        before=before,
        after=result,
        request=request,
        metadata={
            "module": "i18n",
        },
        is_restorable=True,
    )

    return result


@router.get(
    "/i18n/translations",
    response_model=(
        I18nTranslationListResponse
    ),
)
def list_translations(
    locale_code: str | None = Query(
        default=None,
    ),
    namespace: str | None = Query(
        default=None,
    ),
    search: str | None = Query(
        default=None,
    ),
    is_active: bool | None = Query(
        default=None,
    ),
    skip: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=1000,
    ),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    return (
        i18n_admin_service
        .list_translations(
            db,
            locale_code=locale_code,
            namespace=namespace,
            search=search,
            is_active=is_active,
            skip=skip,
            limit=limit,
        )
    )


@router.post(
    "/i18n/translations",
    response_model=(
        I18nTranslationResponse
    ),
    status_code=status.HTTP_201_CREATED,
)
def create_translation(
    data: I18nTranslationCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    result = (
        i18n_admin_service
        .create_translation(
            db,
            data=data,
        )
    )

    audit_entry_service.safe_record(
        db,
        action="create",
        entity_type="i18n_translation",
        entity_id=result.id,
        actor=current_admin,
        before=None,
        after=result,
        request=request,
        metadata={
            "module": "i18n",
            "locale_code": (
                result.locale_code
            ),
            "translation_key": (
                result.translation_key
            ),
        },
    )

    return result


@router.put(
    "/i18n/translations/{translation_id}",
    response_model=(
        I18nTranslationResponse
    ),
)
def update_translation(
    translation_id: int,
    data: I18nTranslationUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    current_list = (
        i18n_admin_service
        .list_translations(
            db,
            skip=0,
            limit=1000,
        )
    )

    before = next(
        (
            item
            for item
            in current_list.items
            if item.id == translation_id
        ),
        None,
    )

    result = (
        i18n_admin_service
        .update_translation(
            db,
            translation_id=translation_id,
            data=data,
        )
    )

    audit_entry_service.safe_record(
        db,
        action="update",
        entity_type="i18n_translation",
        entity_id=result.id,
        actor=current_admin,
        before=before,
        after=result,
        request=request,
        metadata={
            "module": "i18n",
            "locale_code": (
                result.locale_code
            ),
            "translation_key": (
                result.translation_key
            ),
        },
        is_restorable=True,
    )

    return result


@router.post(
    "/i18n/seed",
    response_model=I18nSeedResponse,
)
def seed_initial_i18n_data(
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    result = (
        i18n_admin_service
        .seed_initial_data(db)
    )

    audit_entry_service.safe_record(
        db,
        action="execute",
        entity_type="i18n_seed",
        entity_id=None,
        actor=current_admin,
        before=None,
        after=result,
        request=request,
        metadata={
            "module": "i18n",
        },
    )

    return result