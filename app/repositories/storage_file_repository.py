from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.storage_file import StorageFile
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

    def list_all(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[StorageFile]:
        statement = (
            select(StorageFile)
            .order_by(StorageFile.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        return list(db.execute(statement).scalars().all())

    def count_all(self, db: Session) -> int:
        statement = select(func.count()).select_from(StorageFile)
        return int(db.execute(statement).scalar_one())


storage_file_repository = StorageFileRepository()