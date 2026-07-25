from app.common.cache_enums import CacheNamespace


class CacheTtlPolicyService:
    """
    Central TTL policy for the distributed cache.

    PostgreSQL remains the source of truth. These values only determine
    how long Redis may retain reusable copies of application data.
    """

    DEFAULT_TTL_SECONDS = 300

    NAMESPACE_TTLS: dict[str, int] = {
        CacheNamespace.SYSTEM.value: 300,
        CacheNamespace.SETTINGS.value: 300,
        CacheNamespace.FEATURE_FLAGS.value: 120,
        CacheNamespace.PRICING.value: 180,
        CacheNamespace.TOKEN_PACKAGES.value: 300,
        CacheNamespace.SUBSCRIPTION_PLANS.value: 300,
        CacheNamespace.WORKFLOWS.value: 300,
        CacheNamespace.USERS.value: 300,
        CacheNamespace.BILLING.value: 120,
        CacheNamespace.TRYON.value: 900,
        CacheNamespace.INTEGRATIONS.value: 300,
        CacheNamespace.RUNPOD.value: 10,
        CacheNamespace.STORAGE.value: 900,
        CacheNamespace.ANALYTICS.value: 120,
        CacheNamespace.SECURITY.value: 300,
        CacheNamespace.API.value: 60,
    }

    NEGATIVE_CACHE_TTL_SECONDS = 30
    ACTIVE_JOB_PROGRESS_TTL_SECONDS = 3600
    TERMINAL_JOB_PROGRESS_TTL_SECONDS = 900
    RUNPOD_ACTIVE_STATUS_TTL_SECONDS = 2
    RUNPOD_TERMINAL_STATUS_TTL_SECONDS = 300
    INTEGRATION_HEALTH_TTL_SECONDS = 20
    DISTRIBUTED_LOCK_TTL_SECONDS = 30

    MIN_TTL_SECONDS = 1
    MAX_TTL_SECONDS = 86400

    def _namespace_value(
        self,
        namespace: CacheNamespace | str,
    ) -> str:
        if isinstance(namespace, CacheNamespace):
            return namespace.value

        return str(namespace)

    def ttl_for_namespace(
        self,
        namespace: CacheNamespace | str,
    ) -> int:
        namespace_value = self._namespace_value(
            namespace
        )

        return self.NAMESPACE_TTLS.get(
            namespace_value,
            self.DEFAULT_TTL_SECONDS,
        )

    def clamp(
        self,
        ttl_seconds: int,
        *,
        allow_persistent: bool = False,
    ) -> int:
        if allow_persistent and ttl_seconds <= 0:
            return 0

        return min(
            max(
                int(ttl_seconds),
                self.MIN_TTL_SECONDS,
            ),
            self.MAX_TTL_SECONDS,
        )

    def all_policies(
        self,
    ) -> dict[str, int]:
        return dict(
            self.NAMESPACE_TTLS
        )


cache_ttl_policy_service = (
    CacheTtlPolicyService()
)