from sqlalchemy.orm import Session

from app.common.exceptions import ConflictException, NotFoundException
from app.models.feature_permission import FeaturePermission
from app.models.rbac_permission import RbacPermission
from app.models.rbac_role import RbacRole
from app.models.rbac_role_permission import RbacRolePermission
from app.models.rbac_user_role import RbacUserRole
from app.models.user import User
from app.repositories.feature_permission_repository import feature_permission_repository
from app.repositories.rbac_permission_repository import rbac_permission_repository
from app.repositories.rbac_role_permission_repository import rbac_role_permission_repository
from app.repositories.rbac_role_repository import rbac_role_repository
from app.repositories.rbac_user_role_repository import rbac_user_role_repository
from app.repositories.user_repository import user_repository
from app.schemas.rbac import (
    FeaturePermissionCreate,
    FeaturePermissionUpdate,
    RbacPermissionCreate,
    RbacPermissionUpdate,
    RbacRoleCreate,
    RbacRoleUpdate,
    RbacRoleWithPermissionsResponse,
    UserRbacResponse,
)


class RbacService:
    def list_roles(self, db: Session) -> list[RbacRole]:
        return rbac_role_repository.list_all(db)

    def create_role(self, db: Session, data: RbacRoleCreate) -> RbacRole:
        existing = rbac_role_repository.get_by_key(db, data.key)

        if existing:
            raise ConflictException("Role key already exists.")

        return rbac_role_repository.create(db, data=data.model_dump())

    def update_role(self, db: Session, role_id: int, data: RbacRoleUpdate) -> RbacRole:
        role = rbac_role_repository.get_by_id(db, role_id)

        if not role:
            raise NotFoundException("Role not found.")

        return rbac_role_repository.update(
            db,
            db_obj=role,
            data=data.model_dump(exclude_unset=True),
        )

    def list_permissions(self, db: Session) -> list[RbacPermission]:
        return rbac_permission_repository.list_all(db)

    def create_permission(
        self,
        db: Session,
        data: RbacPermissionCreate,
    ) -> RbacPermission:
        existing = rbac_permission_repository.get_by_key(db, data.key)

        if existing:
            raise ConflictException("Permission key already exists.")

        return rbac_permission_repository.create(db, data=data.model_dump())

    def update_permission(
        self,
        db: Session,
        permission_id: int,
        data: RbacPermissionUpdate,
    ) -> RbacPermission:
        permission = rbac_permission_repository.get_by_id(db, permission_id)

        if not permission:
            raise NotFoundException("Permission not found.")

        return rbac_permission_repository.update(
            db,
            db_obj=permission,
            data=data.model_dump(exclude_unset=True),
        )

    def assign_permission_to_role(
        self,
        db: Session,
        *,
        role_id: int,
        permission_id: int,
    ) -> RbacRolePermission:
        role = rbac_role_repository.get_by_id(db, role_id)

        if not role:
            raise NotFoundException("Role not found.")

        permission = rbac_permission_repository.get_by_id(db, permission_id)

        if not permission:
            raise NotFoundException("Permission not found.")

        existing = rbac_role_permission_repository.get_existing(
            db,
            role_id=role_id,
            permission_id=permission_id,
        )

        if existing:
            return existing

        return rbac_role_permission_repository.create(
            db,
            data={
                "role_id": role_id,
                "permission_id": permission_id,
            },
        )

    def remove_permission_from_role(
        self,
        db: Session,
        *,
        role_id: int,
        permission_id: int,
    ) -> None:
        rbac_role_permission_repository.delete_existing(
            db,
            role_id=role_id,
            permission_id=permission_id,
        )

    def get_role_with_permissions(
        self,
        db: Session,
        role_id: int,
    ) -> RbacRoleWithPermissionsResponse:
        role = rbac_role_repository.get_by_id(db, role_id)

        if not role:
            raise NotFoundException("Role not found.")

        permissions = rbac_role_permission_repository.list_permissions_by_role_id(
            db,
            role_id,
        )

        return RbacRoleWithPermissionsResponse(
            id=role.id,
            key=role.key,
            name=role.name,
            description=role.description,
            is_system=role.is_system,
            is_active=role.is_active,
            created_at=role.created_at,
            updated_at=role.updated_at,
            permissions=permissions,
        )

    def assign_role_to_user(
        self,
        db: Session,
        *,
        user_id: int,
        role_id: int,
    ) -> RbacUserRole:
        user = user_repository.get_by_id(db, user_id)

        if not user:
            raise NotFoundException("User not found.")

        role = rbac_role_repository.get_by_id(db, role_id)

        if not role:
            raise NotFoundException("Role not found.")

        existing = rbac_user_role_repository.get_existing(
            db,
            user_id=user_id,
            role_id=role_id,
        )

        if existing:
            return existing

        return rbac_user_role_repository.create(
            db,
            data={
                "user_id": user_id,
                "role_id": role_id,
            },
        )

    def remove_role_from_user(
        self,
        db: Session,
        *,
        user_id: int,
        role_id: int,
    ) -> None:
        rbac_user_role_repository.delete_existing(
            db,
            user_id=user_id,
            role_id=role_id,
        )

    def get_user_rbac(
        self,
        db: Session,
        user: User,
    ) -> UserRbacResponse:
        role_keys = set()
        permission_keys = set()

        if user.is_superuser or user.role == "superadmin":
            permission_keys.add("superadmin.all")
            role_keys.add("superadmin")

        if user.role:
            role_keys.add(user.role)

        dynamic_roles = rbac_user_role_repository.list_roles_by_user_id(db, user.id)

        for role in dynamic_roles:
            if not role.is_active:
                continue

            role_keys.add(role.key)

            permissions = rbac_role_permission_repository.list_permissions_by_role_id(
                db,
                role.id,
            )

            for permission in permissions:
                if permission.is_active:
                    permission_keys.add(permission.key)

        if user.role in ["admin", "superadmin"]:
            permission_keys.add("admin.panel")

        return UserRbacResponse(
            user_id=user.id,
            role_keys=sorted(list(role_keys)),
            permission_keys=sorted(list(permission_keys)),
        )

    def user_has_permission(
        self,
        db: Session,
        user: User,
        permission_key: str,
    ) -> bool:
        if user.is_superuser or user.role == "superadmin":
            return True

        user_rbac = self.get_user_rbac(db, user)

        return (
            permission_key in user_rbac.permission_keys
            or "superadmin.all" in user_rbac.permission_keys
        )

    def list_feature_permissions(self, db: Session) -> list[FeaturePermission]:
        return feature_permission_repository.list_all(db)

    def list_public_feature_permissions(self, db: Session) -> dict[str, bool]:
        features = feature_permission_repository.list_public(db)
        return {feature.key: feature.is_enabled for feature in features}

    def create_feature_permission(
        self,
        db: Session,
        data: FeaturePermissionCreate,
    ) -> FeaturePermission:
        key = str(data.key.value if hasattr(data.key, "value") else data.key)

        existing = feature_permission_repository.get_by_key(db, key)

        if existing:
            raise ConflictException("Feature permission key already exists.")

        payload = data.model_dump()
        payload["key"] = key

        return feature_permission_repository.create(db, data=payload)

    def update_feature_permission(
        self,
        db: Session,
        feature_id: int,
        data: FeaturePermissionUpdate,
    ) -> FeaturePermission:
        feature = feature_permission_repository.get_by_id(db, feature_id)

        if not feature:
            raise NotFoundException("Feature permission not found.")

        return feature_permission_repository.update(
            db,
            db_obj=feature,
            data=data.model_dump(exclude_unset=True),
        )


rbac_service = RbacService()