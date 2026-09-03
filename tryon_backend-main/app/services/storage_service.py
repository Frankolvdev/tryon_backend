from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.common.enums import StorageProvider
from app.common.exceptions import ConflictException, NotFoundException
from app.core.config import settings
from app.models.storage_file import StorageFile
from app.repositories.storage_file_repository import storage_file_repository
from app.services.runtime_settings_service import runtime_settings_service
from app.services.s3_storage_service import s3_storage_service


class StorageService:
    REMOTE_PROVIDERS = {
        StorageProvider.S3.value,
        StorageProvider.AMAZON_S3.value,
        StorageProvider.CLOUDFLARE_R2.value,
    }
    ACTIVE_ALIASES = {
        "s3": StorageProvider.AMAZON_S3.value,
        "amazon": StorageProvider.AMAZON_S3.value,
        "amazon_s3": StorageProvider.AMAZON_S3.value,
        "r2": StorageProvider.CLOUDFLARE_R2.value,
        "cloudflare": StorageProvider.CLOUDFLARE_R2.value,
        "cloudflare_r2": StorageProvider.CLOUDFLARE_R2.value,
        "local": StorageProvider.LOCAL.value,
    }

    def _local_storage_dir(self, db: Session | None = None) -> str:
        return settings.LOCAL_STORAGE_DIR if db is None else runtime_settings_service.local_storage_dir(db)

    def _ensure_local_storage_dir(self, db: Session | None = None) -> Path:
        path=Path(self._local_storage_dir(db)); path.mkdir(parents=True, exist_ok=True); return path

    @staticmethod
    def _normalize_object_key(object_key: str) -> str:
        value=object_key.replace("\\", "/").lstrip("/")
        if ".." in Path(value).parts: raise ConflictException("Invalid object key.")
        return value

    def _local_public_url(self, object_key: str) -> str:
        return "/local-files/" + self._normalize_object_key(object_key)

    def active_provider(self, db: Session) -> str:
        raw=(runtime_settings_service.storage_provider(db) or "local").strip().lower()
        provider=self.ACTIVE_ALIASES.get(raw, raw)
        if provider not in {StorageProvider.LOCAL.value, StorageProvider.AMAZON_S3.value, StorageProvider.CLOUDFLARE_R2.value}:
            raise ConflictException(f"Unsupported active storage provider: {raw}")
        return provider

    def provider_for_file(self, storage_file: StorageFile) -> str:
        # Historical 's3' rows always remain bound to the legacy S3/Amazon config.
        return str(storage_file.provider or StorageProvider.LOCAL.value)

    def save_bytes(self, db: Session, *, user_id: int | None, content: bytes, original_filename: str,
                   content_type: str | None, folder: str) -> StorageFile:
        provider=self.active_provider(db)
        return self._save_local(db, user_id=user_id, content=content, original_filename=original_filename,
                                content_type=content_type, folder=folder) if provider == StorageProvider.LOCAL.value else                self._save_remote(db, provider=provider, user_id=user_id, content=content,
                                 original_filename=original_filename, content_type=content_type, folder=folder)

    def save_upload_file(self, db: Session, *, user_id: int | None, file: UploadFile, folder: str) -> StorageFile:
        content=file.file.read(); max_bytes=runtime_settings_service.max_upload_size_mb(db)*1024*1024
        if len(content)>max_bytes: raise ConflictException(f"File is too large. Max upload size is {runtime_settings_service.max_upload_size_mb(db)} MB.")
        return self.save_bytes(db, user_id=user_id, content=content, original_filename=file.filename or "upload.bin",
                               content_type=file.content_type, folder=folder)

    def _object_key(self, folder: str, original_filename: str) -> str:
        return self._normalize_object_key(f"{folder}/{uuid4().hex}{Path(original_filename).suffix}")

    def _save_local(self, db: Session, *, user_id: int | None, content: bytes, original_filename: str,
                    content_type: str | None, folder: str) -> StorageFile:
        key=self._object_key(folder, original_filename); path=self._ensure_local_storage_dir(db)/key
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
        return storage_file_repository.create(db, data={"user_id":user_id,"provider":StorageProvider.LOCAL.value,"bucket":None,
            "object_key":key,"public_url":self._local_public_url(key),"original_filename":original_filename,
            "content_type":content_type,"size_bytes":len(content)})

    def _save_remote(self, db: Session, *, provider: str, user_id: int | None, content: bytes,
                     original_filename: str, content_type: str | None, folder: str) -> StorageFile:
        key=self._object_key(folder, original_filename)
        uploaded=s3_storage_service.upload_bytes(db, provider=provider, content=content, object_key=key, content_type=content_type)
        return storage_file_repository.create(db, data={"user_id":user_id,"provider":provider,"bucket":uploaded["bucket"],
            "object_key":uploaded["object_key"],"public_url":uploaded["public_url"] or None,
            "original_filename":original_filename,"content_type":content_type,"size_bytes":uploaded["size_bytes"]})

    def read_bytes(self, db: Session, *, storage_file: StorageFile) -> bytes:
        provider=self.provider_for_file(storage_file)
        if provider == StorageProvider.LOCAL.value:
            path=self._ensure_local_storage_dir(db)/self._normalize_object_key(storage_file.object_key)
            if not path.is_file(): raise NotFoundException("Stored file content was not found.")
            return path.read_bytes()
        if provider in self.REMOTE_PROVIDERS:
            return s3_storage_service.read_bytes(db, provider=provider, bucket=storage_file.bucket, object_key=storage_file.object_key)
        raise ConflictException(f"Unsupported stored file provider: {provider}")

    def create_local_copy_result(self, db: Session, *, user_id: int, source_file: StorageFile, folder: str) -> StorageFile:
        return self.save_bytes(db, user_id=user_id, content=self.read_bytes(db, storage_file=source_file),
                               original_filename=source_file.original_filename or f"result{Path(source_file.object_key).suffix or '.jpg'}",
                               content_type=source_file.content_type or "image/jpeg", folder=folder)

    def create_remote_result_record(self, db: Session, *, user_id: int, public_url: str, folder: str,
                                    original_filename: str, content_type: str) -> StorageFile:
        # External URLs are references, not objects managed by a configured bucket.
        key=self._normalize_object_key(f"{folder}/{uuid4().hex}{Path(original_filename).suffix}")
        provider=StorageProvider.S3.value if public_url.startswith(("http://","https://")) else StorageProvider.LOCAL.value
        return storage_file_repository.create(db, data={"user_id":user_id,"provider":provider,"bucket":None,"object_key":key,
            "public_url":public_url,"original_filename":original_filename,"content_type":content_type,"size_bytes":0})

    def create_presigned_url(self, db: Session, *, storage_file: StorageFile, expires_in_seconds: int = 3600) -> str | None:
        provider=self.provider_for_file(storage_file)
        if provider == StorageProvider.LOCAL.value: return storage_file.public_url or self._local_public_url(storage_file.object_key)
        if provider in self.REMOTE_PROVIDERS:
            return s3_storage_service.create_presigned_url(db, provider=provider, bucket=storage_file.bucket,
                object_key=storage_file.object_key, expires_in_seconds=expires_in_seconds)
        return storage_file.public_url

    def delete_file(self, db: Session, *, storage_file: StorageFile) -> None:
        provider=self.provider_for_file(storage_file)
        if provider == StorageProvider.LOCAL.value:
            path=self._ensure_local_storage_dir(db)/self._normalize_object_key(storage_file.object_key)
            if path.exists(): path.unlink()
            return
        if provider in self.REMOTE_PROVIDERS:
            s3_storage_service.delete_file(db, provider=provider, bucket=storage_file.bucket, object_key=storage_file.object_key)
            return
        raise ConflictException(f"Unsupported stored file provider: {provider}")

    def health_check(self, db: Session, *, provider: str | None = None) -> dict:
        selected=self.ACTIVE_ALIASES.get((provider or self.active_provider(db)).lower(), provider or self.active_provider(db))
        if selected == StorageProvider.LOCAL.value:
            root = self._ensure_local_storage_dir(db)
            probe = root / ".storage-health-check"
            probe.write_bytes(b"ok")
            probe.unlink()
            return {
                "healthy": True,
                "provider": selected,
                "directory": str(root),
                "message": f"Almacenamiento local disponible en {root}.",
            }

        result = s3_storage_service.health_check(db, provider=selected)
        result.setdefault(
            "message",
            f"Conexión correcta con {selected} y acceso confirmado al bucket {result.get('bucket', '')}.",
        )
        return result

storage_service=StorageService()
