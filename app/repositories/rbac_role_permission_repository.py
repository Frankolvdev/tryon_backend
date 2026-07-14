from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.rbac_permission import RbacPermission
from app.models.rbac_role_permission import RbacRolePermission
from app.repositories.base import BaseRepository


class RbacRolePermissionRepository(BaseRepository[RbacRolePermission]):
    def __init__(self):
        super().__init__(RbacRolePermission)

    def get_existing(
        self,
        db: Session,
        *,
        role_id: int,
        permission_id: int,
    ) -> RbacRolePermission | None:
        statement = (
            select(RbacRolePermission)
            .where(RbacRolePermission.role_id == role_id)
            .where(RbacRolePermission.permission_id == permission_id)
        )

        return db.execute(statement).scalar_one_or_none()

    def list_permissions_by_role_id(
        self,
        db: Session,
        role_id: int,
    ) -> list[RbacPermission]:
        statement = (
            select(RbacPermission)
            .join(
                RbacRolePermission,
                RbacRolePermission.permission_id == RbacPermission.id,
            )
            .where(RbacRolePermission.role_id == role_id)
            .order_by(RbacPermission.key.asc())
        )

        return list(db.execute(statement).scalars().all())

    def delete_existing(
        self,
        db: Session,
        *,
        role_id: int,
        permission_id: int,
    ) -> None:
        existing = self.get_existing(
            db,
            role_id=role_id,
            permission_id=permission_id,
        )

        if existing:
            db.delete(existing)
            db.commit()


rbac_role_permission_repository = RbacRolePermissionRepository()