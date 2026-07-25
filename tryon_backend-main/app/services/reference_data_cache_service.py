from collections.abc import Callable
from typing import Any, TypeVar

from app.common.cache_enums import CacheNamespace
from app.services.distributed_cache_service import (
    distributed_cache_service,
)


T = TypeVar("T")


class ReferenceDataCacheService:
    SETTINGS_TTL = 300
    FEATURE_FLAGS_TTL = 120
    PRICING_TTL = 180
    SUBSCRIPTION_PLANS_TTL = 300
    TOKEN_PACKAGES_TTL = 300
    WORKFLOWS_TTL = 300

    def remember_settings(
        self,
        *,
        key: str,
        loader: Callable[[], T],
        ttl_seconds: int | None = None,
    ) -> T:
        return distributed_cache_service.remember(
            namespace=CacheNamespace.SETTINGS,
            parts=["setting", key],
            loader=loader,
            ttl_seconds=(
                ttl_seconds
                or self.SETTINGS_TTL
            ),
            tags=[
                "system-settings",
                f"system-setting:{key}",
            ],
        )

    def remember_optional_setting(
        self,
        *,
        key: str,
        loader: Callable[[], T | None],
        ttl_seconds: int | None = None,
    ) -> T | None:
        return (
            distributed_cache_service
            .remember_optional(
                namespace=CacheNamespace.SETTINGS,
                parts=["setting", key],
                loader=loader,
                ttl_seconds=(
                    ttl_seconds
                    or self.SETTINGS_TTL
                ),
                negative_ttl_seconds=30,
                tags=[
                    "system-settings",
                    f"system-setting:{key}",
                ],
            )
        )

    def remember_feature_flag(
        self,
        *,
        key: str,
        loader: Callable[[], T | None],
        ttl_seconds: int | None = None,
    ) -> T | None:
        return (
            distributed_cache_service
            .remember_optional(
                namespace=(
                    CacheNamespace.FEATURE_FLAGS
                ),
                parts=["flag", key],
                loader=loader,
                ttl_seconds=(
                    ttl_seconds
                    or self.FEATURE_FLAGS_TTL
                ),
                negative_ttl_seconds=30,
                tags=[
                    "feature-flags",
                    f"feature-flag:{key}",
                ],
            )
        )

    def remember_feature_flag_list(
        self,
        *,
        scope: str,
        loader: Callable[[], T],
        ttl_seconds: int | None = None,
    ) -> T:
        return distributed_cache_service.remember(
            namespace=(
                CacheNamespace.FEATURE_FLAGS
            ),
            parts=["list", scope],
            loader=loader,
            ttl_seconds=(
                ttl_seconds
                or self.FEATURE_FLAGS_TTL
            ),
            tags=[
                "feature-flags",
                f"feature-flags-scope:{scope}",
            ],
        )

    def remember_pricing(
        self,
        *,
        pricing_key: str,
        loader: Callable[[], T | None],
        ttl_seconds: int | None = None,
    ) -> T | None:
        return (
            distributed_cache_service
            .remember_optional(
                namespace=CacheNamespace.PRICING,
                parts=["rule", pricing_key],
                loader=loader,
                ttl_seconds=(
                    ttl_seconds
                    or self.PRICING_TTL
                ),
                negative_ttl_seconds=30,
                tags=[
                    "pricing",
                    f"pricing-rule:{pricing_key}",
                ],
            )
        )

    def remember_pricing_list(
        self,
        *,
        scope: str,
        loader: Callable[[], T],
        ttl_seconds: int | None = None,
    ) -> T:
        return distributed_cache_service.remember(
            namespace=CacheNamespace.PRICING,
            parts=["list", scope],
            loader=loader,
            ttl_seconds=(
                ttl_seconds
                or self.PRICING_TTL
            ),
            tags=[
                "pricing",
                f"pricing-scope:{scope}",
            ],
        )

    def remember_subscription_plan(
        self,
        *,
        plan_id: int,
        loader: Callable[[], T | None],
        ttl_seconds: int | None = None,
    ) -> T | None:
        return (
            distributed_cache_service
            .remember_optional(
                namespace=(
                    CacheNamespace
                    .SUBSCRIPTION_PLANS
                ),
                parts=["plan", plan_id],
                loader=loader,
                ttl_seconds=(
                    ttl_seconds
                    or self.SUBSCRIPTION_PLANS_TTL
                ),
                negative_ttl_seconds=30,
                tags=[
                    "subscription-plans",
                    f"subscription-plan:{plan_id}",
                ],
            )
        )

    def remember_subscription_plan_list(
        self,
        *,
        scope: str,
        loader: Callable[[], T],
        ttl_seconds: int | None = None,
    ) -> T:
        return distributed_cache_service.remember(
            namespace=(
                CacheNamespace.SUBSCRIPTION_PLANS
            ),
            parts=["list", scope],
            loader=loader,
            ttl_seconds=(
                ttl_seconds
                or self.SUBSCRIPTION_PLANS_TTL
            ),
            tags=[
                "subscription-plans",
                f"subscription-plan-scope:{scope}",
            ],
        )

    def remember_token_package(
        self,
        *,
        package_id: int,
        loader: Callable[[], T | None],
        ttl_seconds: int | None = None,
    ) -> T | None:
        return (
            distributed_cache_service
            .remember_optional(
                namespace=(
                    CacheNamespace.TOKEN_PACKAGES
                ),
                parts=["package", package_id],
                loader=loader,
                ttl_seconds=(
                    ttl_seconds
                    or self.TOKEN_PACKAGES_TTL
                ),
                negative_ttl_seconds=30,
                tags=[
                    "token-packages",
                    f"token-package:{package_id}",
                ],
            )
        )

    def remember_token_package_list(
        self,
        *,
        scope: str,
        loader: Callable[[], T],
        ttl_seconds: int | None = None,
    ) -> T:
        return distributed_cache_service.remember(
            namespace=(
                CacheNamespace.TOKEN_PACKAGES
            ),
            parts=["list", scope],
            loader=loader,
            ttl_seconds=(
                ttl_seconds
                or self.TOKEN_PACKAGES_TTL
            ),
            tags=[
                "token-packages",
                f"token-package-scope:{scope}",
            ],
        )

    def remember_workflow(
        self,
        *,
        workflow_id: int,
        loader: Callable[[], T | None],
        workflow_key: str | None = None,
        category: str | None = None,
        ttl_seconds: int | None = None,
    ) -> T | None:
        tags = [
            "workflows",
            f"workflow-id:{workflow_id}",
        ]

        if workflow_key:
            tags.append(
                f"workflow:{workflow_key}"
            )

        if category:
            tags.append(
                f"workflow-category:{category}"
            )

        return (
            distributed_cache_service
            .remember_optional(
                namespace=CacheNamespace.WORKFLOWS,
                parts=["id", workflow_id],
                loader=loader,
                ttl_seconds=(
                    ttl_seconds
                    or self.WORKFLOWS_TTL
                ),
                negative_ttl_seconds=30,
                tags=tags,
            )
        )

    def remember_workflow_by_key(
        self,
        *,
        workflow_key: str,
        loader: Callable[[], T | None],
        ttl_seconds: int | None = None,
    ) -> T | None:
        return (
            distributed_cache_service
            .remember_optional(
                namespace=CacheNamespace.WORKFLOWS,
                parts=[
                    "latest-active",
                    workflow_key,
                ],
                loader=loader,
                ttl_seconds=(
                    ttl_seconds
                    or self.WORKFLOWS_TTL
                ),
                negative_ttl_seconds=30,
                tags=[
                    "workflows",
                    f"workflow:{workflow_key}",
                ],
            )
        )

    def remember_default_workflow(
        self,
        *,
        category: str,
        loader: Callable[[], T | None],
        ttl_seconds: int | None = None,
    ) -> T | None:
        return (
            distributed_cache_service
            .remember_optional(
                namespace=CacheNamespace.WORKFLOWS,
                parts=[
                    "default",
                    category,
                ],
                loader=loader,
                ttl_seconds=(
                    ttl_seconds
                    or self.WORKFLOWS_TTL
                ),
                negative_ttl_seconds=30,
                tags=[
                    "workflows",
                    f"workflow-category:{category}",
                ],
            )
        )

    def remember_workflow_list(
        self,
        *,
        filters: dict[str, Any],
        loader: Callable[[], T],
        ttl_seconds: int | None = None,
    ) -> T:
        return distributed_cache_service.remember(
            namespace=CacheNamespace.WORKFLOWS,
            parts=[
                "list",
                filters,
            ],
            loader=loader,
            ttl_seconds=(
                ttl_seconds
                or self.WORKFLOWS_TTL
            ),
            tags=[
                "workflows",
            ],
        )


reference_data_cache_service = (
    ReferenceDataCacheService()
)