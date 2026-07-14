from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.system_setting import SystemSetting
from app.repositories.base import BaseRepository


class SystemSettingRepository(BaseRepository[SystemSetting]):
    def __init__(self):
        super().__init__(SystemSetting)

    def get_by_key(
        self,
        db: Session,
        key: str,
    ) -> SystemSetting | None:
        statement = select(SystemSetting).where(SystemSetting.key == key)
        return db.execute(statement).scalar_one_or_none()

    def list_all(self, db: Session) -> list[SystemSetting]:
        statement = (
            select(SystemSetting)
            .order_by(SystemSetting.category.asc(), SystemSetting.sort_order.asc(), SystemSetting.key.asc())
        )
        return list(db.execute(statement).scalars().all())

    def list_by_category(
        self,
        db: Session,
        category: str,
    ) -> list[SystemSetting]:
        statement = (
            select(SystemSetting)
            .where(SystemSetting.category == category)
            .order_by(SystemSetting.sort_order.asc(), SystemSetting.key.asc())
        )
        return list(db.execute(statement).scalars().all())

    def list_public(self, db: Session) -> list[SystemSetting]:
        statement = (
            select(SystemSetting)
            .where(SystemSetting.is_public.is_(True))
            .order_by(SystemSetting.category.asc(), SystemSetting.sort_order.asc(), SystemSetting.key.asc())
        )
        return list(db.execute(statement).scalars().all())


system_setting_repository = SystemSettingRepository()