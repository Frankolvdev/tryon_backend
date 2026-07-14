from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
    status,
)
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.auth_guard import (
    auth_guard,
)
from app.models.user import User
from app.schemas.user_gallery import (
    UserGalleryComparisonResponse,
    UserGalleryDownloadResponse,
    UserGalleryItemCreate,
    UserGalleryItemResponse,
    UserGalleryItemUpdate,
    UserGalleryListResponse,
    UserGalleryOperationResponse,
)
from app.services.activity_service import (
    activity_service,
)
from app.services.user_gallery_service import (
    user_gallery_service,
)


router = APIRouter()


@router.post(
    "",
    response_model=UserGalleryItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_gallery_item(
    data: UserGalleryItemCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    result = user_gallery_service.create_item(
        db,
        user=current_user,
        data=data,
    )

    activity_service.create_log(
        db,
        user_id=current_user.id,
        action="gallery_item_created",
        description=(
            "User added an item "
            "to the gallery."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return result


@router.get(
    "",
    response_model=UserGalleryListResponse,
)
def list_gallery_items(
    favorite: bool | None = Query(
        default=None,
    ),
    archived: bool | None = Query(
        default=False,
    ),
    category: str | None = Query(
        default=None,
    ),
    search: str | None = Query(
        default=None,
    ),
    include_deleted: bool = Query(
        default=False,
    ),
    skip: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    return user_gallery_service.list_items(
        db,
        user=current_user,
        favorite=favorite,
        archived=archived,
        category=category,
        search=search,
        include_deleted=include_deleted,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{gallery_item_id}",
    response_model=UserGalleryItemResponse,
)
def get_gallery_item(
    gallery_item_id: int,
    include_deleted: bool = Query(
        default=False,
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    return user_gallery_service.get_item(
        db,
        user=current_user,
        gallery_item_id=gallery_item_id,
        include_deleted=include_deleted,
    )


@router.patch(
    "/{gallery_item_id}",
    response_model=UserGalleryItemResponse,
)
def update_gallery_item(
    gallery_item_id: int,
    data: UserGalleryItemUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    result = user_gallery_service.update_item(
        db,
        user=current_user,
        gallery_item_id=gallery_item_id,
        data=data,
    )

    activity_service.create_log(
        db,
        user_id=current_user.id,
        action="gallery_item_updated",
        description=(
            "User updated a gallery item."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return result


@router.post(
    "/{gallery_item_id}/favorite",
    response_model=UserGalleryItemResponse,
)
def toggle_gallery_favorite(
    gallery_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    return user_gallery_service.toggle_favorite(
        db,
        user=current_user,
        gallery_item_id=gallery_item_id,
    )


@router.get(
    "/{gallery_item_id}/comparison",
    response_model=(
        UserGalleryComparisonResponse
    ),
)
def get_gallery_comparison(
    gallery_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    return user_gallery_service.comparison(
        db,
        user=current_user,
        gallery_item_id=gallery_item_id,
    )


@router.get(
    "/{gallery_item_id}/download",
    response_model=(
        UserGalleryDownloadResponse
    ),
)
def get_gallery_download_url(
    gallery_item_id: int,
    file_type: str = Query(
        default="result",
        pattern="^(source|result)$",
    ),
    expires_in_seconds: int = Query(
        default=900,
        ge=60,
        le=86400,
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    return user_gallery_service.download_url(
        db,
        user=current_user,
        gallery_item_id=gallery_item_id,
        file_type=file_type,
        expires_in_seconds=(
            expires_in_seconds
        ),
    )


@router.delete(
    "/{gallery_item_id}",
    response_model=(
        UserGalleryOperationResponse
    ),
)
def delete_gallery_item(
    gallery_item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    result = user_gallery_service.delete_item(
        db,
        user=current_user,
        gallery_item_id=gallery_item_id,
    )

    activity_service.create_log(
        db,
        user_id=current_user.id,
        action="gallery_item_deleted",
        description=(
            "User deleted a gallery item."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return result


@router.post(
    "/{gallery_item_id}/restore",
    response_model=UserGalleryItemResponse,
)
def restore_gallery_item(
    gallery_item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        auth_guard
    ),
):
    result = user_gallery_service.restore_item(
        db,
        user=current_user,
        gallery_item_id=gallery_item_id,
    )

    activity_service.create_log(
        db,
        user_id=current_user.id,
        action="gallery_item_restored",
        description=(
            "User restored a gallery item."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return result