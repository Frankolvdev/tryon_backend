from pathlib import Path
from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.exceptions import ConflictException, NotFoundException
from app.models.storage_file import StorageFile
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.services.storage_service import storage_service

DEFAULT_LIBRARY_QUOTA_MB = 1024
QUOTA_KEY = "user_library_quota_mb"

class UserLibraryService:
    def quota_bytes(self, db: Session) -> int:
        setting = db.scalar(select(SystemSetting).where(SystemSetting.key == QUOTA_KEY))
        value = getattr(setting, "value_integer", None) if setting else None
        return int(value or DEFAULT_LIBRARY_QUOTA_MB) * 1024 * 1024

    def set_quota_mb(self, db: Session, quota_mb: int) -> int:
        setting = db.scalar(select(SystemSetting).where(SystemSetting.key == QUOTA_KEY))
        if setting is None:
            setting = SystemSetting(
                category="storage", key=QUOTA_KEY, label="Cuota de librería por usuario",
                description="Espacio máximo disponible por usuario final.", value_type="integer",
                value_integer=quota_mb, default_value_integer=DEFAULT_LIBRARY_QUOTA_MB,
                is_public=True, is_editable=True, is_sensitive=False, requires_restart=False, sort_order=95,
            )
            db.add(setting)
        else:
            setting.value_integer = quota_mb
        db.commit()
        return quota_mb

    def _query(self, user_id: int):
        return select(StorageFile).where(
            StorageFile.user_id == user_id,
            StorageFile.object_key.like("user-library/%"),
        )

    def usage(self, db: Session, user_id: int) -> dict:
        used, count = db.execute(
            select(func.coalesce(func.sum(StorageFile.size_bytes), 0), func.count(StorageFile.id)).where(
                StorageFile.user_id == user_id,
                StorageFile.object_key.like("user-library/%"),
            )
        ).one()
        quota = self.quota_bytes(db)
        used = int(used or 0)
        return {"used_bytes": used, "quota_bytes": quota, "available_bytes": max(0, quota-used),
                "percent_used": round((used/quota)*100, 2) if quota else 100.0, "file_count": int(count or 0)}

    def _url(self, db: Session, item: StorageFile) -> str:
        return storage_service.create_presigned_url(db, storage_file=item, expires_in_seconds=3600) or item.public_url or ""

    def response(self, db: Session, item: StorageFile) -> dict:
        return {"id": item.id, "filename": item.original_filename or Path(item.object_key).name,
                "content_type": item.content_type, "size_bytes": int(item.size_bytes or 0),
                "provider": item.provider, "url": self._url(db,item), "created_at": item.created_at}

    def list(self, db: Session, user: User, search: str|None=None, content_type: str|None=None, limit: int=100):
        q=self._query(user.id).order_by(StorageFile.created_at.desc()).limit(limit)
        if search: q=q.where(StorageFile.original_filename.ilike(f"%{search.strip()}%"))
        if content_type: q=q.where(StorageFile.content_type.like(f"{content_type}%"))
        items=list(db.scalars(q).all())
        return {"items":[self.response(db,x) for x in items], "usage":self.usage(db,user.id)}

    def upload(self, db: Session, user: User, file: UploadFile):
        content=file.file.read(); file.file.seek(0)
        usage=self.usage(db,user.id)
        if usage["used_bytes"] + len(content) > usage["quota_bytes"]:
            raise ConflictException("Tu librería no tiene espacio suficiente. Elimina archivos para continuar.")
        # Dedupe safely by filename+size for this user. Existing file is reused instead of duplicated.
        existing=db.scalar(self._query(user.id).where(StorageFile.original_filename==(file.filename or "upload.bin"), StorageFile.size_bytes==len(content)).limit(1))
        if existing is not None:
            return self.response(db, existing)
        saved=storage_service.save_bytes(db,user_id=user.id,content=content,original_filename=file.filename or "upload.bin",content_type=file.content_type,folder=f"user-library/{user.id}")
        return self.response(db,saved)

    def get_owned(self, db: Session, user: User, file_id: int) -> StorageFile:
        item=db.scalar(self._query(user.id).where(StorageFile.id==file_id))
        if item is None: raise NotFoundException("Library file not found.")
        return item

    def delete(self, db: Session, user: User, file_id: int):
        item=self.get_owned(db,user,file_id)
        storage_service.delete_file(db=db,storage_file=item)
        db.delete(item); db.commit()

    def clear(self, db: Session, user: User):
        items=list(db.scalars(self._query(user.id)).all())
        for item in items:
            storage_service.delete_file(db=db,storage_file=item); db.delete(item)
        db.commit(); return len(items)

user_library_service=UserLibraryService()
