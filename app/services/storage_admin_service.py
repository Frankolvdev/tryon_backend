from sqlalchemy.orm import Session

from app.common.exceptions import NotFoundException
from app.models.storage_file import StorageFile
from app.repositories.storage_file_repository import storage_file_repository


class StorageAdminService:
    def list_files(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[StorageFile]:
        return storage_file_repository.list_all(
            db,
            skip=skip,
            limit=limit,
        )

    def get_file(
        self,
        db: Session,
        file_id: int,
    ) -> StorageFile:
        file_obj = storage_file_repository.get_by_id(db, file_id)

        if not file_obj:
            raise NotFoundException("Storage file not found.")

        return file_obj


storage_admin_service = StorageAdminService()