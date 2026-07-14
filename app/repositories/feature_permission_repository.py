from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.feature_permission import FeaturePermission
from app.repositories.base import BaseRepository


class FeaturePermissionRepository(BaseRepository[FeaturePermission]):
    def __init__(self):
        super().__init__(FeaturePermission)

    def get_by_key(self, db: Session, key: str) -> FeaturePermission | None:
        statement = select(FeaturePermission).where(FeaturePermission.key == key)
        return db.execute(statement).scalar_one_or_none()

    def list_all(self, db: Session) -> list[FeaturePermission]:
        statement = select(FeaturePermission).order_by(FeaturePermission.key.asc())
        return list(db.execute(statement).scalars().all())

    def list_public(self, db: Session) -> list[FeaturePermission]:
        statement = (
            select(FeaturePermission)
            .where(FeaturePermission.is_public.is_(True))
            .order_by(FeaturePermission.key.asc())
        )
        return list(db.execute(statement).scalars().all())


feature_permission_repository = FeaturePermissionRepository()