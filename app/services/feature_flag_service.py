from sqlalchemy.orm import Session

from app.common.exceptions import ConflictException, NotFoundException
from app.models.feature_flag import FeatureFlag
from app.repositories.feature_flag_repository import feature_flag_repository
from app.schemas.feature_flag import FeatureFlagCreate, FeatureFlagUpdate


class FeatureFlagService:
    def list_flags(self, db: Session) -> list[FeatureFlag]:
        return feature_flag_repository.list_all(db)

    def list_public_flags(self, db: Session) -> dict[str, bool]:
        flags = feature_flag_repository.list_public(db)
        return {flag.key: flag.is_enabled for flag in flags}

    def create_flag(
        self,
        db: Session,
        data: FeatureFlagCreate,
    ) -> FeatureFlag:
        existing = feature_flag_repository.get_by_key(db, data.key)

        if existing:
            raise ConflictException("Feature flag key already exists.")

        return feature_flag_repository.create(
            db,
            data=data.model_dump(),
        )

    def update_flag(
        self,
        db: Session,
        flag_id: int,
        data: FeatureFlagUpdate,
    ) -> FeatureFlag:
        flag = feature_flag_repository.get_by_id(db, flag_id)

        if not flag:
            raise NotFoundException("Feature flag not found.")

        return feature_flag_repository.update(
            db,
            db_obj=flag,
            data=data.model_dump(exclude_unset=True),
        )

    def is_enabled(
        self,
        db: Session,
        key: str,
        default: bool = False,
    ) -> bool:
        flag = feature_flag_repository.get_by_key(db, key)

        if not flag:
            return default

        return flag.is_enabled


feature_flag_service = FeatureFlagService()