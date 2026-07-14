from app.common.cache_enums import (
    CacheNamespace,
)
from app.services.distributed_cache_service import (
    distributed_cache_service,
)


class CacheInvalidationService:
    def invalidate_user(
        self,
        user_id: int,
        *,
        email: str | None = None,
    ) -> None:
        distributed_cache_service.invalidate_tag(
            tag=f"user:{user_id}"
        )

        distributed_cache_service.invalidate_tag(
            tag=f"user-permissions:{user_id}"
        )

        if email:
            distributed_cache_service.invalidate_tag(
                tag=(
                    f"user-email:"
                    f"{email.strip().lower()}"
                )
            )

    def invalidate_user_sessions(
        self,
        user_id: int,
    ) -> None:
        distributed_cache_service.invalidate_tag(
            tag=f"user:{user_id}"
        )

    def invalidate_rbac(
        self,
        *,
        user_id: int | None = None,
    ) -> None:
        distributed_cache_service.invalidate_tag(
            tag="rbac"
        )

        if user_id is not None:
            distributed_cache_service.invalidate_tag(
                tag=(
                    f"user-permissions:"
                    f"{user_id}"
                )
            )

        distributed_cache_service.invalidate_namespace(
            namespace=CacheNamespace.SECURITY
        )

    def invalidate_api_responses(
        self,
        *,
        endpoint_name: str | None = None,
    ) -> None:
        distributed_cache_service.invalidate_tag(
            tag="api-responses"
        )

        if endpoint_name:
            distributed_cache_service.invalidate_tag(
                tag=(
                    f"api-endpoint:"
                    f"{endpoint_name}"
                )
            )

        distributed_cache_service.invalidate_namespace(
            namespace=CacheNamespace.API
        )

    def invalidate_system_settings(
        self,
        *,
        setting_key: str | None = None,
    ) -> None:
        distributed_cache_service.invalidate_tag(
            tag="system-settings"
        )

        if setting_key:
            distributed_cache_service.invalidate_tag(
                tag=(
                    f"system-setting:"
                    f"{setting_key}"
                )
            )

        distributed_cache_service.invalidate_namespace(
            namespace=CacheNamespace.SETTINGS
        )

    def invalidate_feature_flags(
        self,
        *,
        flag_key: str | None = None,
        scope: str | None = None,
    ) -> None:
        distributed_cache_service.invalidate_tag(
            tag="feature-flags"
        )

        if flag_key:
            distributed_cache_service.invalidate_tag(
                tag=(
                    f"feature-flag:"
                    f"{flag_key}"
                )
            )

        if scope:
            distributed_cache_service.invalidate_tag(
                tag=(
                    f"feature-flags-scope:"
                    f"{scope}"
                )
            )

        distributed_cache_service.invalidate_namespace(
            namespace=CacheNamespace.FEATURE_FLAGS
        )

    def invalidate_pricing(
        self,
        *,
        pricing_key: str | None = None,
        scope: str | None = None,
    ) -> None:
        distributed_cache_service.invalidate_tag(
            tag="pricing"
        )

        if pricing_key:
            distributed_cache_service.invalidate_tag(
                tag=(
                    f"pricing-rule:"
                    f"{pricing_key}"
                )
            )

        if scope:
            distributed_cache_service.invalidate_tag(
                tag=(
                    f"pricing-scope:"
                    f"{scope}"
                )
            )

        distributed_cache_service.invalidate_namespace(
            namespace=CacheNamespace.PRICING
        )

    def invalidate_subscription_plans(
        self,
        *,
        plan_id: int | None = None,
        scope: str | None = None,
    ) -> None:
        distributed_cache_service.invalidate_tag(
            tag="subscription-plans"
        )

        if plan_id is not None:
            distributed_cache_service.invalidate_tag(
                tag=(
                    f"subscription-plan:"
                    f"{plan_id}"
                )
            )

        if scope:
            distributed_cache_service.invalidate_tag(
                tag=(
                    "subscription-plan-scope:"
                    f"{scope}"
                )
            )

        distributed_cache_service.invalidate_namespace(
            namespace=(
                CacheNamespace.SUBSCRIPTION_PLANS
            )
        )

    def invalidate_token_packages(
        self,
        *,
        package_id: int | None = None,
        scope: str | None = None,
    ) -> None:
        distributed_cache_service.invalidate_tag(
            tag="token-packages"
        )

        if package_id is not None:
            distributed_cache_service.invalidate_tag(
                tag=(
                    f"token-package:"
                    f"{package_id}"
                )
            )

        if scope:
            distributed_cache_service.invalidate_tag(
                tag=(
                    "token-package-scope:"
                    f"{scope}"
                )
            )

        distributed_cache_service.invalidate_namespace(
            namespace=CacheNamespace.TOKEN_PACKAGES
        )

    def invalidate_workflows(
        self,
        *,
        workflow_id: int | None = None,
        workflow_key: str | None = None,
        category: str | None = None,
    ) -> None:
        distributed_cache_service.invalidate_tag(
            tag="workflows"
        )

        if workflow_id is not None:
            distributed_cache_service.invalidate_tag(
                tag=(
                    f"workflow-id:"
                    f"{workflow_id}"
                )
            )

        if workflow_key:
            distributed_cache_service.invalidate_tag(
                tag=f"workflow:{workflow_key}"
            )

        if category:
            distributed_cache_service.invalidate_tag(
                tag=(
                    f"workflow-category:"
                    f"{category}"
                )
            )

        distributed_cache_service.invalidate_namespace(
            namespace=CacheNamespace.WORKFLOWS
        )

    def invalidate_integrations(
        self,
        *,
        provider: str | None = None,
    ) -> None:
        distributed_cache_service.invalidate_tag(
            tag="integrations"
        )

        if provider:
            distributed_cache_service.invalidate_tag(
                tag=f"integration:{provider}"
            )

        distributed_cache_service.invalidate_namespace(
            namespace=CacheNamespace.INTEGRATIONS
        )

    def invalidate_all_reference_data(
        self,
    ) -> None:
        namespaces = [
            CacheNamespace.SETTINGS,
            CacheNamespace.FEATURE_FLAGS,
            CacheNamespace.PRICING,
            CacheNamespace.SUBSCRIPTION_PLANS,
            CacheNamespace.TOKEN_PACKAGES,
            CacheNamespace.WORKFLOWS,
            CacheNamespace.INTEGRATIONS,
        ]

        for namespace in namespaces:
            distributed_cache_service.invalidate_namespace(
                namespace=namespace
            )


cache_invalidation_service = (
    CacheInvalidationService()
)