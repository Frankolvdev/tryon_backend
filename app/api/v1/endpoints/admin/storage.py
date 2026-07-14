from fastapi import APIRouter, Depends, Query, UploadFile, File
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.repositories.storage_file_repository import storage_file_repository
from app.schemas.storage_file import StorageFileResponse
from app.services.storage_service import storage_service

router = APIRouter()


@router.get("/storage/files", response_model=list[StorageFileResponse])
def list_storage_files(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
):
    return storage_file_repository.list_all(
        db,
        skip=skip,
        limit=limit,
    )


@router.post("/storage/test-upload", response_model=StorageFileResponse)
def test_storage_upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return storage_service.save_upload_file(
        db=db,
        user_id=current_admin.id,
        file=file,
        folder="admin-test-uploads",
    )


@router.get("/storage/files/{storage_file_id}/signed-url")
def create_storage_signed_url(
    storage_file_id: int,
    expires_in_seconds: int = Query(default=3600, ge=60, le=86400),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    storage_file = storage_file_repository.get_by_id(db, storage_file_id)

    if not storage_file:
        from app.common.exceptions import NotFoundException
        raise NotFoundException("Storage file not found.")

    return {
        "url": storage_service.create_presigned_url(
            db=db,
            storage_file=storage_file,
            expires_in_seconds=expires_in_seconds,
        )
    }