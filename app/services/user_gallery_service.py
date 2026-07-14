from sqlalchemy.orm import Session

from app.common.exceptions import (
    ConflictException,
    NotFoundException,
)
from app.common.time import utc_now
from app.models.storage_file import StorageFile
from app.models.user import User
from app.models.user_gallery_item import (
    UserGalleryItem,
)
from app.repositories.user_gallery_repository import (
    user_gallery_repository,
)
from app.schemas.user_gallery import (
    UserGalleryComparisonResponse,
    UserGalleryDownloadResponse,
    UserGalleryItemCreate,
    UserGalleryItemResponse,
    UserGalleryItemUpdate,
    UserGalleryListResponse,
    UserGalleryOperationResponse,
)
from app.services.storage_service import (
    storage_service,
)


class UserGalleryService:
    def _get_storage_file(
        self,
        db: Session,
        *,
        file_id: int,
    ) -> StorageFile:
        storage_file = db.get(
            StorageFile,
            file_id,
        )

        if storage_file is None:
            raise NotFoundException(
                "Storage file not found."
            )

        return storage_file

    def _validate_file_owner(
        self,
        *,
        storage_file: StorageFile,
        user_id: int,
    ) -> None:
        if (
            storage_file.user_id is not None
            and storage_file.user_id
            != user_id
        ):
            raise ConflictException(
                "The file does not belong "
                "to this user."
            )

    def _file_url(
        self,
        db: Session,
        *,
        storage_file: StorageFile | None,
    ) -> str | None:
        if storage_file is None:
            return None

        return storage_service.create_presigned_url(
            db,
            storage_file=storage_file,
            expires_in_seconds=3600,
        )

    def _response(
        self,
        db: Session,
        *,
        item: UserGalleryItem,
    ) -> UserGalleryItemResponse:
        source_file = None

        if item.source_file_id is not None:
            source_file = db.get(
                StorageFile,
                item.source_file_id,
            )

        result_file = self._get_storage_file(
            db,
            file_id=item.result_file_id,
        )

        return UserGalleryItemResponse(
            id=item.id,
            user_id=item.user_id,
            tryon_job_id=item.tryon_job_id,
            source_file_id=item.source_file_id,
            result_file_id=item.result_file_id,
            title=item.title,
            description=item.description,
            category=item.category,
            visibility=item.visibility,
            is_favorite=item.is_favorite,
            is_archived=item.is_archived,
            is_deleted=item.is_deleted,
            source_url=self._file_url(
                db,
                storage_file=source_file,
            ),
            result_url=self._file_url(
                db,
                storage_file=result_file,
            )
            or result_file.public_url,
            created_at=item.created_at,
            updated_at=item.updated_at,
            deleted_at=item.deleted_at,
        )

    def create_item(
        self,
        db: Session,
        *,
        user: User,
        data: UserGalleryItemCreate,
    ) -> UserGalleryItemResponse:
        result_file = self._get_storage_file(
            db,
            file_id=data.result_file_id,
        )

        self._validate_file_owner(
            storage_file=result_file,
            user_id=user.id,
        )

        if data.source_file_id is not None:
            source_file = self._get_storage_file(
                db,
                file_id=data.source_file_id,
            )

            self._validate_file_owner(
                storage_file=source_file,
                user_id=user.id,
            )

        if data.tryon_job_id is not None:
            existing = (
                user_gallery_repository
                .get_by_tryon_job(
                    db,
                    user_id=user.id,
                    tryon_job_id=(
                        data.tryon_job_id
                    ),
                )
            )

            if existing is not None:
                return self._response(
                    db,
                    item=existing,
                )

        item = UserGalleryItem(
            user_id=user.id,
            tryon_job_id=data.tryon_job_id,
            source_file_id=data.source_file_id,
            result_file_id=data.result_file_id,
            title=data.title,
            description=data.description,
            category=data.category,
            visibility=data.visibility,
        )

        db.add(item)
        db.commit()
        db.refresh(item)

        return self._response(
            db,
            item=item,
        )

    def list_items(
        self,
        db: Session,
        *,
        user: User,
        favorite: bool | None = None,
        archived: bool | None = False,
        category: str | None = None,
        search: str | None = None,
        include_deleted: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> UserGalleryListResponse:
        items = (
            user_gallery_repository
            .list_for_user(
                db,
                user_id=user.id,
                favorite=favorite,
                archived=archived,
                category=category,
                search=search,
                include_deleted=(
                    include_deleted
                ),
                skip=skip,
                limit=limit,
            )
        )

        total = (
            user_gallery_repository
            .count_for_user(
                db,
                user_id=user.id,
                favorite=favorite,
                archived=archived,
                category=category,
                search=search,
                include_deleted=(
                    include_deleted
                ),
            )
        )

        return UserGalleryListResponse(
            items=[
                self._response(
                    db,
                    item=item,
                )
                for item in items
            ],
            total=total,
            skip=skip,
            limit=limit,
        )

    def get_item(
        self,
        db: Session,
        *,
        user: User,
        gallery_item_id: int,
        include_deleted: bool = False,
    ) -> UserGalleryItemResponse:
        item = (
            user_gallery_repository
            .get_for_user(
                db,
                gallery_item_id=(
                    gallery_item_id
                ),
                user_id=user.id,
                include_deleted=(
                    include_deleted
                ),
            )
        )

        if item is None:
            raise NotFoundException(
                "Gallery item not found."
            )

        return self._response(
            db,
            item=item,
        )

    def update_item(
        self,
        db: Session,
        *,
        user: User,
        gallery_item_id: int,
        data: UserGalleryItemUpdate,
    ) -> UserGalleryItemResponse:
        item = (
            user_gallery_repository
            .get_for_user(
                db,
                gallery_item_id=(
                    gallery_item_id
                ),
                user_id=user.id,
            )
        )

        if item is None:
            raise NotFoundException(
                "Gallery item not found."
            )

        update_data = data.model_dump(
            exclude_unset=True
        )

        for field, value in update_data.items():
            setattr(
                item,
                field,
                value,
            )

        db.add(item)
        db.commit()
        db.refresh(item)

        return self._response(
            db,
            item=item,
        )

    def toggle_favorite(
        self,
        db: Session,
        *,
        user: User,
        gallery_item_id: int,
    ) -> UserGalleryItemResponse:
        item = (
            user_gallery_repository
            .get_for_user(
                db,
                gallery_item_id=(
                    gallery_item_id
                ),
                user_id=user.id,
            )
        )

        if item is None:
            raise NotFoundException(
                "Gallery item not found."
            )

        item.is_favorite = (
            not item.is_favorite
        )

        db.add(item)
        db.commit()
        db.refresh(item)

        return self._response(
            db,
            item=item,
        )

    def delete_item(
        self,
        db: Session,
        *,
        user: User,
        gallery_item_id: int,
    ) -> UserGalleryOperationResponse:
        item = (
            user_gallery_repository
            .get_for_user(
                db,
                gallery_item_id=(
                    gallery_item_id
                ),
                user_id=user.id,
            )
        )

        if item is None:
            raise NotFoundException(
                "Gallery item not found."
            )

        item.is_deleted = True
        item.deleted_at = utc_now()

        db.add(item)
        db.commit()

        return UserGalleryOperationResponse(
            success=True,
            message="Gallery item deleted.",
        )

    def restore_item(
        self,
        db: Session,
        *,
        user: User,
        gallery_item_id: int,
    ) -> UserGalleryItemResponse:
        item = (
            user_gallery_repository
            .get_for_user(
                db,
                gallery_item_id=(
                    gallery_item_id
                ),
                user_id=user.id,
                include_deleted=True,
            )
        )

        if item is None:
            raise NotFoundException(
                "Gallery item not found."
            )

        item.is_deleted = False
        item.deleted_at = None

        db.add(item)
        db.commit()
        db.refresh(item)

        return self._response(
            db,
            item=item,
        )

    def comparison(
        self,
        db: Session,
        *,
        user: User,
        gallery_item_id: int,
    ) -> UserGalleryComparisonResponse:
        item = (
            user_gallery_repository
            .get_for_user(
                db,
                gallery_item_id=(
                    gallery_item_id
                ),
                user_id=user.id,
            )
        )

        if item is None:
            raise NotFoundException(
                "Gallery item not found."
            )

        source_file = None

        if item.source_file_id is not None:
            source_file = db.get(
                StorageFile,
                item.source_file_id,
            )

        result_file = self._get_storage_file(
            db,
            file_id=item.result_file_id,
        )

        return UserGalleryComparisonResponse(
            gallery_item_id=item.id,
            source_url=self._file_url(
                db,
                storage_file=source_file,
            ),
            result_url=self._file_url(
                db,
                storage_file=result_file,
            )
            or result_file.public_url,
        )

    def download_url(
        self,
        db: Session,
        *,
        user: User,
        gallery_item_id: int,
        file_type: str = "result",
        expires_in_seconds: int = 900,
    ) -> UserGalleryDownloadResponse:
        item = (
            user_gallery_repository
            .get_for_user(
                db,
                gallery_item_id=(
                    gallery_item_id
                ),
                user_id=user.id,
            )
        )

        if item is None:
            raise NotFoundException(
                "Gallery item not found."
            )

        if file_type == "source":
            if item.source_file_id is None:
                raise NotFoundException(
                    "Source image is not available."
                )

            file_id = item.source_file_id

        elif file_type == "result":
            file_id = item.result_file_id

        else:
            raise ConflictException(
                "Invalid gallery file type."
            )

        storage_file = self._get_storage_file(
            db,
            file_id=file_id,
        )

        self._validate_file_owner(
            storage_file=storage_file,
            user_id=user.id,
        )

        download_url = (
            storage_service
            .create_presigned_url(
                db,
                storage_file=storage_file,
                expires_in_seconds=(
                    expires_in_seconds
                ),
            )
        )

        return UserGalleryDownloadResponse(
            gallery_item_id=item.id,
            file_id=file_id,
            download_url=download_url,
            expires_in_seconds=(
                expires_in_seconds
            ),
        )


user_gallery_service = (
    UserGalleryService()
)