from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.feature_flag import FeatureFlag
from app.repositories.base import BaseRepository


class FeatureFlagRepository(BaseRepository[FeatureFlag]):
    def __init__(self):
        super().__init__(FeatureFlag)

    def get_by_key(
        self,
        db: Session,
        key: str,
    ) -> FeatureFlag | None:
        statement = select(FeatureFlag).where(FeatureFlag.key == key)
        return db.execute(statement).scalar_one_or_none()

    def list_all(self, db: Session) -> list[FeatureFlag]:
        statement = select(FeatureFlag).order_by(FeatureFlag.key.asc())
        return list(db.execute(statement).scalars().all())

    def list_public(self, db: Session) -> list[FeatureFlag]:
        statement = (
            select(FeatureFlag)
            .where(FeatureFlag.is_public.is_(True))
            .order_by(FeatureFlag.key.asc())
        )
        return list(db.execute(statement).scalars().all())


feature_flag_repository = FeatureFlagRepository()