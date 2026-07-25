from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.models.storage_file import StorageFile
from app.models.user import User
from app.repositories.base import BaseRepository


class StorageFileRepository(BaseRepository[StorageFile]):
    def __init__(self):
        super().__init__(StorageFile)

    def list_by_user_id(
        self,
        db: Session,
        user_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> list[StorageFile]:
        statement = (
            select(StorageFile)
            .where(StorageFile.user_id == user_id)
            .order_by(StorageFile.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(db.execute(statement).scalars().all())

    def list_admin_filtered(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        user: str | None = None,
        role: str | None = None,
        provider: str | None = None,
        file_type: str | None = None,
    ) -> list[dict]:
        statement = (
            select(StorageFile, User)
            .outerjoin(User, User.id == StorageFile.user_id)
            .order_by(StorageFile.created_at.desc())
        )

        if provider:
            statement = statement.where(StorageFile.provider == provider)

        if role:
            if role == "system":
                statement = statement.where(StorageFile.user_id.is_(None))
            else:
                statement = statement.where(User.role == role)

        if user:
            normalized_user = user.strip().lower()
            user_conditions = [
                func.lower(func.coalesce(User.email, "")).contains(normalized_user),
                func.lower(func.coalesce(User.full_name, "")).contains(normalized_user),
            ]
            if normalized_user.isdigit():
                user_conditions.append(StorageFile.user_id == int(normalized_user))
            statement = statement.where(or_(*user_conditions))

        if file_type:
            content_type = func.lower(func.coalesce(StorageFile.content_type, ""))
            if file_type == "images":
                statement = statement.where(content_type.like("image/%"))
            elif file_type == "videos":
                statement = statement.where(content_type.like("video/%"))
            elif file_type == "documents":
                statement = statement.where(
                    or_(
                        content_type.like("application/pdf%"),
                        content_type.like("text/%"),
                        content_type.like("application/msword%"),
                        content_type.like("application/vnd.openxmlformats-officedocument%"),
                    )
                )
            elif file_type == "archives":
                statement = statement.where(
                    or_(
                        content_type.like("application/zip%"),
                        content_type.like("application/x-rar%"),
                        content_type.like("application/x-7z%"),
                        content_type.like("application/gzip%"),
                    )
                )
            elif file_type == "other":
                statement = statement.where(
                    ~content_type.like("image/%"),
                    ~content_type.like("video/%"),
                )

        if search:
            value = f"%{search.strip().lower()}%"
            conditions = [
                func.lower(func.coalesce(StorageFile.original_filename, "")).like(value),
                func.lower(StorageFile.object_key).like(value),
                func.lower(func.coalesce(StorageFile.bucket, "")).like(value),
                func.lower(func.coalesce(StorageFile.content_type, "")).like(value),
                func.lower(func.coalesce(User.email, "")).like(value),
                func.lower(func.coalesce(User.full_name, "")).like(value),
                cast(StorageFile.id, String).like(value),
            ]
            statement = statement.where(or_(*conditions))

        rows = db.execute(statement.offset(skip).limit(limit)).all()
        return [
            {
                "id": storage_file.id,
                "user_id": storage_file.user_id,
                "user_email": user_obj.email if user_obj else None,
                "user_full_name": user_obj.full_name if user_obj else None,
                "user_role": user_obj.role if user_obj else None,
                "provider": storage_file.provider,
                "bucket": storage_file.bucket,
                "object_key": storage_file.object_key,
                "public_url": storage_file.public_url,
                "original_filename": storage_file.original_filename,
                "content_type": storage_file.content_type,
                "size_bytes": storage_file.size_bytes,
                "created_at": storage_file.created_at,
            }
            for storage_file, user_obj in rows
        ]

    def list_all(self, db: Session, *, skip: int = 0, limit: int = 100) -> list[StorageFile]:
        statement = select(StorageFile).order_by(StorageFile.created_at.desc()).offset(skip).limit(limit)
        return list(db.execute(statement).scalars().all())

    def count_all(self, db: Session) -> int:
        statement = select(func.count()).select_from(StorageFile)
        return int(db.execute(statement).scalar_one())


storage_file_repository = StorageFileRepository()
