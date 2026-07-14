from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.rbac_permission import RbacPermission
from app.repositories.base import BaseRepository


class RbacPermissionRepository(BaseRepository[RbacPermission]):
    def __init__(self):
        super().__init__(RbacPermission)

    def get_by_key(self, db: Session, key: str) -> RbacPermission | None:
        statement = select(RbacPermission).where(RbacPermission.key == key)
        return db.execute(statement).scalar_one_or_none()

    def list_all(self, db: Session) -> list[RbacPermission]:
        statement = select(RbacPermission).order_by(
            RbacPermission.module.asc(),
            RbacPermission.action.asc(),
            RbacPermission.key.asc(),
        )
        return list(db.execute(statement).scalars().all())


rbac_permission_repository = RbacPermissionRepository()