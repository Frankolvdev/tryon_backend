from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.rbac_role import RbacRole
from app.repositories.base import BaseRepository


class RbacRoleRepository(BaseRepository[RbacRole]):
    def __init__(self):
        super().__init__(RbacRole)

    def get_by_key(self, db: Session, key: str) -> RbacRole | None:
        statement = select(RbacRole).where(RbacRole.key == key)
        return db.execute(statement).scalar_one_or_none()

    def list_all(self, db: Session) -> list[RbacRole]:
        statement = select(RbacRole).order_by(RbacRole.key.asc())
        return list(db.execute(statement).scalars().all())


rbac_role_repository = RbacRoleRepository()