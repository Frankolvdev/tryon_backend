from typing import Any

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from pydantic import BaseModel, Field
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.common.enums import IntegrationProvider
from app.common.exceptions import ConflictException, NotFoundException
from app.models.user import User
from app.repositories.storage_file_repository import storage_file_repository
from app.schemas.storage_file import StorageFileResponse
from app.services.audit_service import audit_service
from app.services.integration_service import integration_service
from app.services.runtime_settings_service import runtime_settings_service
from app.services.storage_service import storage_service
from app.repositories.system_setting_repository import system_setting_repository

router = APIRouter()

class StorageProviderUpdate(BaseModel):
    active_provider: str | None = None
    local_storage_dir: str | None = Field(default=None, min_length=1, max_length=1000)
    name: str | None = Field(default=None, min_length=2, max_length=255)
    is_enabled: bool | None = None
    base_url: str | None = None
    api_key: str | None = None
    api_secret: str | None = None
    config: dict[str, Any] | None = None


def _integration_payload(db: Session, provider: IntegrationProvider) -> dict[str, Any]:
    config = integration_service.get_config_response(db, provider)
    return {
        "provider": config.provider.value,
        "name": config.name,
        "is_enabled": config.is_enabled,
        "status": config.status.value,
        "base_url": config.base_url,
        "api_key_configured": config.api_key_configured,
        "api_secret_configured": config.api_secret_configured,
        "config": config.config,
        "last_health_status": config.last_health_status,
        "last_health_message": config.last_health_message,
        "last_checked_at": config.last_checked_at,
    }



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

    content = storage_service.read_bytes(db, storage_file=storage_file)
    headers = {"Content-Disposition": f'{disposition}; filename="{filename}"'}
    return Response(content=content, media_type=storage_file.content_type or "application/octet-stream", headers=headers)


@router.get("/storage/providers")
def list_storage_providers(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    active = storage_service.active_provider(db)
    return {
        "active_provider": active,
        "local": {
            "provider": "local",
            "name": "Almacenamiento local",
            "is_enabled": True,
            "status": "enabled",
            "local_storage_dir": runtime_settings_service.local_storage_dir(db),
            "last_health_status": "healthy",
            "last_health_message": "El directorio local se crea automáticamente si no existe.",
        },
        "amazon_s3": _integration_payload(db, IntegrationProvider.AMAZON_S3),
        "cloudflare_r2": _integration_payload(db, IntegrationProvider.CLOUDFLARE_R2),
        "providers": [
            {"key": "local", "label": "Local", "active": active == "local"},
            {"key": "amazon_s3", "label": "Amazon S3", "active": active == "amazon_s3"},
            {"key": "cloudflare_r2", "label": "Cloudflare R2", "active": active == "cloudflare_r2"},
        ],
        "note": "Cambiar el proveedor activo solo afecta archivos nuevos. Los existentes conservan su proveedor original.",
    }


@router.post("/storage/providers/{provider}/health")
def check_storage_provider(
    provider: str,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return storage_service.health_check(db, provider=provider)


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


@router.patch("/storage/providers/{provider}")
def update_storage_provider(
    provider: str,
    data: StorageProviderUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    normalized = storage_service.ACTIVE_ALIASES.get(provider.strip().lower(), provider.strip().lower())
    if normalized not in {"local", "amazon_s3", "cloudflare_r2"}:
        raise ConflictException("Unsupported storage provider.")

    if normalized == "local":
        if data.local_storage_dir is not None:
            setting = system_setting_repository.get_by_key(db, "local_storage_dir")
            if not setting:
                raise NotFoundException("local_storage_dir setting not found.")
            system_setting_repository.update(db, db_obj=setting, data={"value_string": data.local_storage_dir})
    else:
        enum_provider = IntegrationProvider.AMAZON_S3 if normalized == "amazon_s3" else IntegrationProvider.CLOUDFLARE_R2
        from app.schemas.integration import IntegrationConfigUpdate
        integration_service.update_config(
            db=db,
            provider=enum_provider,
            data=IntegrationConfigUpdate(
                name=data.name,
                is_enabled=data.is_enabled,
                base_url=data.base_url,
                api_key=data.api_key,
                api_secret=data.api_secret,
                config=data.config,
            ),
        )

    if data.active_provider is not None:
        selected = storage_service.ACTIVE_ALIASES.get(data.active_provider.strip().lower(), data.active_provider.strip().lower())
        if selected not in {"local", "amazon_s3", "cloudflare_r2"}:
            raise ConflictException("Unsupported active storage provider.")
        setting = system_setting_repository.get_by_key(db, "storage_provider")
        if not setting:
            raise NotFoundException("storage_provider setting not found.")
        system_setting_repository.update(db, db_obj=setting, data={"value_string": selected})

    audit_service.create_log(
        db, actor_user_id=current_admin.id, action="admin_storage_provider_updated",
        entity_type="storage_provider", entity_id=normalized,
        description=f"Admin updated storage provider {normalized}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return list_storage_providers(db=db, current_admin=current_admin)
