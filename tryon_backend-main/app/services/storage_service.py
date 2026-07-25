from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.common.enums import IntegrationProvider, StorageProvider
from app.common.exceptions import ConflictException
from app.core.config import settings
from app.models.storage_file import StorageFile
from app.repositories.storage_file_repository import (
    storage_file_repository,
)
from app.services.integration_service import integration_service
from app.services.runtime_settings_service import (
    runtime_settings_service,
)


class StorageService:
    def _local_storage_dir(
        self,
        db: Session | None = None,
    ) -> str:
        if db is None:
            return settings.LOCAL_STORAGE_DIR

        return runtime_settings_service.local_storage_dir(db)

    def _ensure_local_storage_dir(
        self,
        db: Session | None = None,
    ) -> Path:
        storage_dir = Path(
            self._local_storage_dir(db)
        )

        storage_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        return storage_dir

    def _normalize_object_key(
        self,
        object_key: str,
    ) -> str:
        return object_key.replace("\\", "/")

    def _local_public_url(
        self,
        object_key: str,
    ) -> str:
        normalized_object_key = (
            self._normalize_object_key(
                object_key
            )
        )

        return (
            "/local-files/"
            + normalized_object_key
        )

    def _s3_enabled(
        self,
        db: Session,
    ) -> bool:
        try:
            config = integration_service.get_config(
                db,
                IntegrationProvider.S3,
            )

            return bool(config.is_enabled)

        except Exception:
            return False

    def save_bytes(
        self,
        db: Session,
        *,
        user_id: int | None,
        content: bytes,
        original_filename: str,
        content_type: str | None,
        folder: str,
    ) -> StorageFile:
        if self._s3_enabled(db):
            return self._save_upload_file_s3(
                db=db, user_id=user_id, content=content,
                original_filename=original_filename, content_type=content_type, folder=folder,
            )
        return self._save_upload_file_local(
            db=db, user_id=user_id, content=content,
            original_filename=original_filename, content_type=content_type, folder=folder,
        )

    def save_upload_file(
        self,
        db: Session,
        *,
        user_id: int | None,
        file: UploadFile,
        folder: str,
    ) -> StorageFile:
        max_upload_size_mb = (
            runtime_settings_service
            .max_upload_size_mb(db)
        )

        original_filename = (
            file.filename
            or "upload.bin"
        )

        content = file.file.read()

        max_bytes = (
            max_upload_size_mb
            * 1024
            * 1024
        )

        if len(content) > max_bytes:
            raise ConflictException(
                "File is too large. "
                f"Max upload size is "
                f"{max_upload_size_mb} MB."
            )

        if self._s3_enabled(db):
            return self._save_upload_file_s3(
                db=db,
                user_id=user_id,
                content=content,
                original_filename=(
                    original_filename
                ),
                content_type=file.content_type,
                folder=folder,
            )

        return self._save_upload_file_local(
            db=db,
            user_id=user_id,
            content=content,
            original_filename=(
                original_filename
            ),
            content_type=file.content_type,
            folder=folder,
        )

    def _save_upload_file_local(
        self,
        db: Session,
        *,
        user_id: int | None,
        content: bytes,
        original_filename: str,
        content_type: str | None,
        folder: str,
    ) -> StorageFile:
        storage_dir = (
            self._ensure_local_storage_dir(db)
            / folder
        )

        storage_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        suffix = Path(
            original_filename
        ).suffix

        object_key = (
            f"{folder}/"
            f"{uuid4().hex}"
            f"{suffix}"
        )

        normalized_object_key = (
            self._normalize_object_key(
                object_key
            )
        )

        destination_path = (
            Path(
                self._local_storage_dir(db)
            )
            / normalized_object_key
        )

        destination_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        destination_path.write_bytes(
            content
        )

        return storage_file_repository.create(
            db,
            data={
                "user_id": user_id,
                "provider": (
                    StorageProvider.LOCAL.value
                ),
                "bucket": None,
                "object_key": (
                    normalized_object_key
                ),
                "public_url": (
                    self._local_public_url(
                        normalized_object_key
                    )
                ),
                "original_filename": (
                    original_filename
                ),
                "content_type": content_type,
                "size_bytes": len(content),
            },
        )

    def _save_upload_file_s3(
        self,
        db: Session,
        *,
        user_id: int | None,
        content: bytes,
        original_filename: str,
        content_type: str | None,
        folder: str,
    ) -> StorageFile:
        from app.services.s3_storage_service import (
            s3_storage_service,
        )

        object_key = (
            s3_storage_service
            .generate_object_key(
                folder=folder,
                original_filename=(
                    original_filename
                ),
            )
        )

        uploaded = (
            s3_storage_service
            .upload_bytes(
                db=db,
                content=content,
                object_key=object_key,
                content_type=content_type,
            )
        )

        return storage_file_repository.create(
            db,
            data={
                "user_id": user_id,
                "provider": (
                    StorageProvider.S3.value
                ),
                "bucket": uploaded["bucket"],
                "object_key": (
                    uploaded["object_key"]
                ),
                "public_url": (
                    uploaded["public_url"]
                ),
                "original_filename": (
                    original_filename
                ),
                "content_type": content_type,
                "size_bytes": (
                    uploaded["size_bytes"]
                ),
            },
        )

    def create_local_copy_result(
        self,
        db: Session,
        *,
        user_id: int,
        source_file: StorageFile,
        folder: str,
    ) -> StorageFile:
        if (
            source_file.provider
            == StorageProvider.S3.value
        ):
            return (
                self.create_remote_result_record(
                    db=db,
                    user_id=user_id,
                    public_url=(
                        source_file.public_url
                    ),
                    folder=folder,
                    original_filename=(
                        source_file
                        .original_filename
                        or "result.jpg"
                    ),
                    content_type=(
                        source_file.content_type
                        or "image/jpeg"
                    ),
                )
            )

        storage_dir = (
            self._ensure_local_storage_dir(db)
            / folder
        )

        storage_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        source_path = (
            Path(
                self._local_storage_dir(db)
            )
            / source_file.object_key
        )

        suffix = (
            Path(
                source_file.object_key
            ).suffix
            or ".jpg"
        )

        object_key = (
            f"{folder}/"
            f"{uuid4().hex}"
            f"{suffix}"
        )

        normalized_object_key = (
            self._normalize_object_key(
                object_key
            )
        )

        destination_path = (
            Path(
                self._local_storage_dir(db)
            )
            / normalized_object_key
        )

        destination_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        destination_path.write_bytes(
            source_path.read_bytes()
        )

        if self._s3_enabled(db):
            from app.services.s3_storage_service import (
                s3_storage_service,
            )

            uploaded = (
                s3_storage_service
                .upload_file(
                    db=db,
                    local_path=str(
                        destination_path
                    ),
                    object_key=(
                        normalized_object_key
                    ),
                    content_type=(
                        source_file.content_type
                    ),
                )
            )

            return storage_file_repository.create(
                db,
                data={
                    "user_id": user_id,
                    "provider": (
                        StorageProvider.S3.value
                    ),
                    "bucket": uploaded["bucket"],
                    "object_key": (
                        uploaded["object_key"]
                    ),
                    "public_url": (
                        uploaded["public_url"]
                    ),
                    "original_filename": (
                        f"result{suffix}"
                    ),
                    "content_type": (
                        source_file.content_type
                    ),
                    "size_bytes": (
                        uploaded["size_bytes"]
                    ),
                },
            )

        return storage_file_repository.create(
            db,
            data={
                "user_id": user_id,
                "provider": (
                    StorageProvider.LOCAL.value
                ),
                "bucket": None,
                "object_key": (
                    normalized_object_key
                ),
                "public_url": (
                    self._local_public_url(
                        normalized_object_key
                    )
                ),
                "original_filename": (
                    f"result{suffix}"
                ),
                "content_type": (
                    source_file.content_type
                ),
                "size_bytes": (
                    destination_path
                    .stat()
                    .st_size
                ),
            },
        )

    def create_remote_result_record(
        self,
        db: Session,
        *,
        user_id: int,
        public_url: str,
        folder: str,
        original_filename: str,
        content_type: str,
    ) -> StorageFile:
        object_key = (
            f"{folder}/remote/"
            f"{uuid4().hex}-"
            f"{original_filename}"
        )

        normalized_object_key = (
            self._normalize_object_key(
                object_key
            )
        )

        provider = (
            StorageProvider.S3.value
            if self._s3_enabled(db)
            else StorageProvider.LOCAL.value
        )

        return storage_file_repository.create(
            db,
            data={
                "user_id": user_id,
                "provider": provider,
                "bucket": None,
                "object_key": (
                    normalized_object_key
                ),
                "public_url": public_url,
                "original_filename": (
                    original_filename
                ),
                "content_type": content_type,
                "size_bytes": 0,
            },
        )

    def create_presigned_url(
        self,
        db: Session,
        *,
        storage_file: StorageFile,
        expires_in_seconds: int = 3600,
    ) -> str:
        if (
            storage_file.provider
            == StorageProvider.S3.value
        ):
            from app.services.s3_storage_service import (
                s3_storage_service,
            )

            return (
                s3_storage_service
                .create_presigned_url(
                    db=db,
                    object_key=(
                        storage_file.object_key
                    ),
                    expires_in_seconds=(
                        expires_in_seconds
                    ),
                )
            )

        return storage_file.public_url

    def delete_file(
        self,
        db: Session,
        *,
        storage_file: StorageFile,
    ) -> None:
        if (
            storage_file.provider
            == StorageProvider.S3.value
        ):
            from app.services.s3_storage_service import (
                s3_storage_service,
            )

            s3_storage_service.delete_file(
                db=db,
                object_key=(
                    storage_file.object_key
                ),
            )

            return

        local_path = (
            Path(
                self._local_storage_dir(db)
            )
            / storage_file.object_key
        )

        if local_path.exists():
            local_path.unlink()


storage_service = StorageService()