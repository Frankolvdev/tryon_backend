from sqlalchemy.orm import Session

from app.common.enums import FeaturePermissionKey, RbacAction, RbacModule
from app.repositories.feature_permission_repository import feature_permission_repository
from app.repositories.rbac_permission_repository import rbac_permission_repository
from app.repositories.rbac_role_repository import rbac_role_repository
from app.schemas.rbac import (
    FeaturePermissionCreate,
    RbacPermissionCreate,
    RbacRoleCreate,
)
from app.services.rbac_service import rbac_service


class DefaultRbacService:
    def seed_permissions(self, db: Session) -> dict:
        created = 0
        skipped = 0

        modules = [
            RbacModule.USERS,
            RbacModule.AUTH,
            RbacModule.TOKENS,
            RbacModule.BILLING,
            RbacModule.SUBSCRIPTIONS,
            RbacModule.TRYON,
            RbacModule.STORAGE,
            RbacModule.PRICING,
            RbacModule.RUNPOD,
            RbacModule.AI,
            RbacModule.ANALYTICS,
            RbacModule.REPORTS,
            RbacModule.SETTINGS,
            RbacModule.FEATURE_FLAGS,
            RbacModule.SYSTEM,
            RbacModule.MONITORING,
            RbacModule.NOTIFICATIONS,
            RbacModule.SUPPORT,
            RbacModule.AUDIT,
            RbacModule.ACTIVITY,
            RbacModule.SCHEDULER,
            RbacModule.SEARCH,
            RbacModule.API_KEYS,
            RbacModule.WEBHOOKS,
            RbacModule.ADMIN,
        ]

        actions = [
            RbacAction.READ,
            RbacAction.CREATE,
            RbacAction.UPDATE,
            RbacAction.DELETE,
            RbacAction.MANAGE,
            RbacAction.EXECUTE,
            RbacAction.EXPORT,
        ]

        for module in modules:
            for action in actions:
                key = f"{module.value}.{action.value}"

                existing = rbac_permission_repository.get_by_key(db, key)

                if existing:
                    skipped += 1
                    continue

                rbac_service.create_permission(
                    db,
                    RbacPermissionCreate(
                        key=key,
                        module=module,
                        action=action,
                        name=f"{module.value.replace('_', ' ').title()} {action.value.title()}",
                        description=f"Allows {action.value} access for {module.value}.",
                        is_system=True,
                        is_active=True,
                    ),
                )

                created += 1

        special_permissions = [
            RbacPermissionCreate(
                key="superadmin.all",
                module=RbacModule.ADMIN,
                action=RbacAction.MANAGE,
                name="Superadmin All",
                description="Full unrestricted access to the entire platform.",
                is_system=True,
                is_active=True,
            ),
            RbacPermissionCreate(
                key="admin.panel",
                module=RbacModule.ADMIN,
                action=RbacAction.READ,
                name="Admin Panel Access",
                description="Allows access to the administration panel.",
                is_system=True,
                is_active=True,
            ),
            RbacPermissionCreate(
                key="billing.refund",
                module=RbacModule.BILLING,
                action=RbacAction.REFUND,
                name="Billing Refund",
                description="Allows issuing refunds.",
                is_system=True,
                is_active=True,
            ),
            RbacPermissionCreate(
                key="users.impersonate",
                module=RbacModule.USERS,
                action=RbacAction.IMPERSONATE,
                name="User Impersonation",
                description="Allows impersonating users for support.",
                is_system=True,
                is_active=True,
            ),
        ]

        for permission in special_permissions:
            existing = rbac_permission_repository.get_by_key(db, permission.key)

            if existing:
                skipped += 1
                continue

            rbac_service.create_permission(db, permission)
            created += 1

        return {
            "permissions_created": created,
            "permissions_skipped": skipped,
        }

    def seed_roles(self, db: Session) -> dict:
        roles = [
            RbacRoleCreate(
                key="superadmin",
                name="Super Admin",
                description="Full platform owner access.",
                is_system=True,
                is_active=True,
            ),
            RbacRoleCreate(
                key="admin",
                name="Admin",
                description="General administrator access.",
                is_system=True,
                is_active=True,
            ),
            RbacRoleCreate(
                key="support",
                name="Support",
                description="Support staff access.",
                is_system=True,
                is_active=True,
            ),
            RbacRoleCreate(
                key="finance",
                name="Finance",
                description="Billing and finance access.",
                is_system=True,
                is_active=True,
            ),
            RbacRoleCreate(
                key="analyst",
                name="Analyst",
                description="Analytics and reports access.",
                is_system=True,
                is_active=True,
            ),
            RbacRoleCreate(
                key="developer",
                name="Developer",
                description="Technical and AI operations access.",
                is_system=True,
                is_active=True,
            ),
            RbacRoleCreate(
                key="user",
                name="User",
                description="Default user role.",
                is_system=True,
                is_active=True,
            ),
        ]

        created = 0
        skipped = 0

        for role in roles:
            existing = rbac_role_repository.get_by_key(db, role.key)

            if existing:
                skipped += 1
                continue

            rbac_service.create_role(db, role)
            created += 1

        return {
            "roles_created": created,
            "roles_skipped": skipped,
        }

    def seed_role_permissions(self, db: Session) -> dict:
        assigned = 0
        skipped = 0

        role_map = {
            "superadmin": ["superadmin.all"],
            "admin": [
                "admin.panel",
                "users.read",
                "users.create",
                "users.update",
                "tokens.read",
                "tokens.update",
                "tryon.read",
                "tryon.update",
                "storage.read",
                "pricing.read",
                "pricing.update",
                "runpod.read",
                "analytics.read",
                "reports.read",
                "reports.export",
                "settings.read",
                "feature_flags.read",
                "system.read",
                "monitoring.read",
                "notifications.read",
                "notifications.update",
                "support.read",
                "support.update",
                "audit.read",
                "activity.read",
                "scheduler.read",
                "scheduler.execute",
                "search.read",
            ],
            "support": [
                "admin.panel",
                "users.read",
                "tryon.read",
                "storage.read",
                "support.read",
                "support.update",
                "notifications.read",
                "activity.read",
                "search.read",
            ],
            "finance": [
                "admin.panel",
                "users.read",
                "tokens.read",
                "billing.read",
                "billing.update",
                "billing.refund",
                "subscriptions.read",
                "subscriptions.update",
                "reports.read",
                "reports.export",
                "analytics.read",
                "search.read",
            ],
            "analyst": [
                "admin.panel",
                "analytics.read",
                "reports.read",
                "reports.export",
                "users.read",
                "tryon.read",
                "tokens.read",
                "billing.read",
                "storage.read",
                "search.read",
            ],
            "developer": [
                "admin.panel",
                "system.read",
                "settings.read",
                "monitoring.read",
                "runpod.read",
                "runpod.update",
                "ai.read",
                "ai.update",
                "tryon.read",
                "tryon.update",
                "scheduler.read",
                "scheduler.execute",
                "audit.read",
                "activity.read",
                "search.read",
            ],
            "user": [],
        }

        for role_key, permission_keys in role_map.items():
            role = rbac_role_repository.get_by_key(db, role_key)

            if not role:
                continue

            for permission_key in permission_keys:
                permission = rbac_permission_repository.get_by_key(db, permission_key)

                if not permission:
                    skipped += 1
                    continue

                existing_permissions = [
                    item.key
                    for item in rbac_service.get_role_with_permissions(db, role.id).permissions
                ]

                if permission.key in existing_permissions:
                    skipped += 1
                    continue

                rbac_service.assign_permission_to_role(
                    db,
                    role_id=role.id,
                    permission_id=permission.id,
                )

                assigned += 1

        return {
            "role_permissions_assigned": assigned,
            "role_permissions_skipped": skipped,
        }

    def seed_feature_permissions(self, db: Session) -> dict:
        features = [
            FeaturePermissionCreate(
                key=FeaturePermissionKey.ADMIN_PANEL,
                name="Admin Panel",
                description="Enables access to the admin panel.",
                is_enabled=True,
                is_public=False,
            ),
            FeaturePermissionCreate(
                key=FeaturePermissionKey.ANALYTICS,
                name="Analytics",
                description="Enables analytics features.",
                is_enabled=True,
                is_public=False,
            ),
            FeaturePermissionCreate(
                key=FeaturePermissionKey.REPORTS,
                name="Reports",
                description="Enables reports.",
                is_enabled=True,
                is_public=False,
            ),
            FeaturePermissionCreate(
                key=FeaturePermissionKey.BILLING,
                name="Billing",
                description="Enables billing features.",
                is_enabled=False,
                is_public=True,
            ),
            FeaturePermissionCreate(
                key=FeaturePermissionKey.SUBSCRIPTIONS,
                name="Subscriptions",
                description="Enables subscriptions.",
                is_enabled=False,
                is_public=True,
            ),
            FeaturePermissionCreate(
                key=FeaturePermissionKey.AI_TRYON,
                name="AI Try-On",
                description="Enables AI try-on generation.",
                is_enabled=True,
                is_public=True,
            ),
            FeaturePermissionCreate(
                key=FeaturePermissionKey.FOOTWEAR_TRYON,
                name="Footwear Try-On",
                description="Enables footwear try-on generation.",
                is_enabled=True,
                is_public=True,
            ),
            FeaturePermissionCreate(
                key=FeaturePermissionKey.HIGH_QUALITY,
                name="High Quality Mode",
                description="Enables high quality generation.",
                is_enabled=True,
                is_public=True,
            ),
            FeaturePermissionCreate(
                key=FeaturePermissionKey.RUNPOD,
                name="RunPod",
                description="Enables RunPod operations.",
                is_enabled=False,
                is_public=False,
            ),
            FeaturePermissionCreate(
                key=FeaturePermissionKey.STORAGE,
                name="Storage",
                description="Enables storage features.",
                is_enabled=True,
                is_public=False,
            ),
            FeaturePermissionCreate(
                key=FeaturePermissionKey.SUPPORT,
                name="Support",
                description="Enables support center.",
                is_enabled=True,
                is_public=True,
            ),
            FeaturePermissionCreate(
                key=FeaturePermissionKey.NOTIFICATIONS,
                name="Notifications",
                description="Enables notifications.",
                is_enabled=True,
                is_public=False,
            ),
            FeaturePermissionCreate(
                key=FeaturePermissionKey.API_KEYS,
                name="API Keys",
                description="Enables API key management.",
                is_enabled=False,
                is_public=False,
            ),
            FeaturePermissionCreate(
                key=FeaturePermissionKey.WEBHOOKS,
                name="Webhooks",
                description="Enables webhook management.",
                is_enabled=False,
                is_public=False,
            ),
        ]

        created = 0
        skipped = 0

        for feature in features:
            key = str(feature.key.value if hasattr(feature.key, "value") else feature.key)
            existing = feature_permission_repository.get_by_key(db, key)

            if existing:
                skipped += 1
                continue

            rbac_service.create_feature_permission(db, feature)
            created += 1

        return {
            "feature_permissions_created": created,
            "feature_permissions_skipped": skipped,
        }

    def seed_all(self, db: Session) -> dict:
        permissions_result = self.seed_permissions(db)
        roles_result = self.seed_roles(db)
        role_permissions_result = self.seed_role_permissions(db)
        feature_permissions_result = self.seed_feature_permissions(db)

        return {
            **permissions_result,
            **roles_result,
            **role_permissions_result,
            **feature_permissions_result,
        }


default_rbac_service = DefaultRbacService()