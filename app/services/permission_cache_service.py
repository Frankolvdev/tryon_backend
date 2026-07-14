from typing import Any

from sqlalchemy.orm import Session

from app.common.cache_enums import CacheNamespace
from app.models.rbac_permission import RbacPermission
from app.models.rbac_role import RbacRole
from app.models.rbac_role_permission import (
    RbacRolePermission,
)
from app.models.rbac_user_role import RbacUserRole
from app.services.cache_stampede_service import (
    cache_stampede_service,
)
from app.services.distributed_cache_service import (
    distributed_cache_service,
)
from sqlalchemy import select


class PermissionCacheService:
    TTL_SECONDS = 300

    def _load_user_permissions(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> dict[str, Any]:
        role_rows = db.execute(
            select(
                RbacRole.id,
                RbacRole.name,
            )
            .join(
                RbacUserRole,
                RbacUserRole.role_id
                == RbacRole.id,
            )
            .where(
                RbacUserRole.user_id
                == user_id
            )
        ).all()

        role_ids = [
            row.id
            for row in role_rows
        ]

        if not role_ids:
            return {
                "user_id": user_id,
                "roles": [],
                "permissions": [],
            }

        permission_rows = db.execute(
            select(
                RbacPermission.id,
                RbacPermission.name,
            )
            .join(
                RbacRolePermission,
                RbacRolePermission.permission_id
                == RbacPermission.id,
            )
            .where(
                RbacRolePermission.role_id.in_(
                    role_ids
                )
            )
            .distinct()
        ).all()

        return {
            "user_id": user_id,
            "roles": [
                {
                    "id": row.id,
                    "name": row.name,
                }
                for row in role_rows
            ],
            "permissions": sorted(
                {
                    row.name
                    for row in permission_rows
                }
            ),
        }

    def get_user_permissions(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> dict[str, Any]:
        return cache_stampede_service.remember(
            namespace=CacheNamespace.SECURITY,
            parts=[
                "user-permissions",
                user_id,
            ],
            loader=lambda: (
                self._load_user_permissions(
                    db,
                    user_id=user_id,
                )
            ),
            ttl_seconds=self.TTL_SECONDS,
            tags=[
                f"user:{user_id}",
                f"user-permissions:{user_id}",
                "rbac",
            ],
        )

    def has_permission(
        self,
        db: Session,
        *,
        user_id: int,
        permission_name: str,
    ) -> bool:
        cached = self.get_user_permissions(
            db,
            user_id=user_id,
        )

        permissions = set(
            cached.get(
                "permissions",
                [],
            )
        )

        return permission_name in permissions

    def invalidate_user(
        self,
        *,
        user_id: int,
    ) -> None:
        distributed_cache_service.invalidate_tag(
            tag=f"user-permissions:{user_id}"
        )

        distributed_cache_service.invalidate_tag(
            tag=f"user:{user_id}"
        )

    def invalidate_all(
        self,
    ) -> None:
        distributed_cache_service.invalidate_tag(
            tag="rbac"
        )

        distributed_cache_service.invalidate_namespace(
            namespace=CacheNamespace.SECURITY
        )


permission_cache_service = (
    PermissionCacheService()
)