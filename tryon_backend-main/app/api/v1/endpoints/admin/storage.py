from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.common.exceptions import ConflictException, NotFoundException
from app.models.user import User
from app.repositories.storage_file_repository import storage_file_repository
from app.schemas.storage_file import StorageFileResponse
from app.services.runtime_settings_service import runtime_settings_service
from app.services.storage_service import storage_service

router = APIRouter()


@router.get("/storage/files", response_model=list[StorageFileResponse])
def list_storage_files(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    search: str | None = Query(default=None, max_length=200),
    user: str | None = Query(default=None, max_length=200),
    role: str | None = Query(default=None, max_length=50),
    provider: str | None = Query(default=None, max_length=50),
    file_type: str | None = Query(default=None, max_length=50),
):
    return storage_file_repository.list_admin_filtered(
        db,
        skip=skip,
        limit=limit,
        search=search,
        user=user,
        role=role,
        provider=provider,
        file_type=file_type,
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
        raise NotFoundException("Storage file not found.")
    return {
        "url": storage_service.create_presigned_url(
            db=db,
            storage_file=storage_file,
            expires_in_seconds=expires_in_seconds,
        )
    }


@router.get("/storage/files/{storage_file_id}/content")
def read_storage_file_content(
    storage_file_id: int,
    download: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    storage_file = storage_file_repository.get_by_id(db, storage_file_id)
    if not storage_file:
        raise NotFoundException("Storage file not found.")

    filename = storage_file.original_filename or f"storage-file-{storage_file.id}"
    disposition = "attachment" if download else "inline"

    if storage_file.provider == "local":
        local_path = Path(runtime_settings_service.local_storage_dir(db)) / storage_file.object_key
        if not local_path.exists() or not local_path.is_file():
            raise NotFoundException("Stored file content was not found.")
        return FileResponse(
            path=str(local_path),
            media_type=storage_file.content_type or "application/octet-stream",
            filename=filename if download else None,
            content_disposition_type=disposition,
        )

    url = storage_service.create_presigned_url(
        db=db,
        storage_file=storage_file,
        expires_in_seconds=3600,
    )
    if not url:
        raise NotFoundException("Storage file URL is not available.")
    return RedirectResponse(url=url, status_code=307)


@router.delete("/storage/files/{storage_file_id}", status_code=204)
def delete_storage_file(
    storage_file_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    storage_file = storage_file_repository.get_by_id(db, storage_file_id)
    if not storage_file:
        raise NotFoundException("Storage file not found.")

    try:
        storage_service.delete_file(db=db, storage_file=storage_file)
        storage_file_repository.delete(db, db_obj=storage_file)
    except Exception as error:
        db.rollback()
        raise ConflictException(
            "The file could not be deleted because it is still referenced or the storage provider rejected the operation."
        ) from error

    return Response(status_code=204)
