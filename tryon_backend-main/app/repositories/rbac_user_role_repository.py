from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.rbac_role import RbacRole
from app.models.rbac_user_role import RbacUserRole
from app.repositories.base import BaseRepository


class RbacUserRoleRepository(BaseRepository[RbacUserRole]):
    def __init__(self):
        super().__init__(RbacUserRole)

    def get_existing(
        self,
        db: Session,
        *,
        user_id: int,
        role_id: int,
    ) -> RbacUserRole | None:
        statement = (
            select(RbacUserRole)
            .where(RbacUserRole.user_id == user_id)
            .where(RbacUserRole.role_id == role_id)
        )

        return db.execute(statement).scalar_one_or_none()

    def list_roles_by_user_id(
        self,
        db: Session,
        user_id: int,
    ) -> list[RbacRole]:
        statement = (
            select(RbacRole)
            .join(
                RbacUserRole,
                RbacUserRole.role_id == RbacRole.id,
            )
            .where(RbacUserRole.user_id == user_id)
            .order_by(RbacRole.key.asc())
        )

        return list(db.execute(statement).scalars().all())

    def delete_existing(
        self,
        db: Session,
        *,
        user_id: int,
        role_id: int,
    ) -> None:
        existing = self.get_existing(
            db,
            user_id=user_id,
            role_id=role_id,
        )

        if existing:
            db.delete(existing)
            db.commit()


rbac_user_role_repository = RbacUserRoleRepository()