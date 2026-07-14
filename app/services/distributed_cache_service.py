import logging
from collections.abc import Callable
from datetime import timedelta
from typing import Any, TypeVar

from redis.exceptions import RedisError

from app.common.cache_enums import (
    CacheNamespace,
    CacheOperation,
)
from app.common.time import utc_now
from app.core.redis_client import redis_client
from app.schemas.cache import (
    CacheDeleteResult,
    CacheGetResult,
    CacheNamespaceInvalidationResult,
    CacheSetResult,
    CacheStatsResponse,
    CacheTagInvalidationResult,
)
from app.services.cache_key_service import (
    cache_key_service,
)
from app.services.cache_serialization_service import (
    cache_serialization_service,
)


logger = logging.getLogger(__name__)


T = TypeVar("T")


class DistributedCacheService:
    DEFAULT_TTL_SECONDS = 300

    STAT_FIELDS = {
        CacheOperation.HIT: "hits",
        CacheOperation.MISS: "misses",
        CacheOperation.SET: "sets",
        CacheOperation.DELETE: "deletes",
        CacheOperation.ERROR: "errors",
    }

    def _namespace_value(
        self,
        namespace: CacheNamespace | str,
    ) -> str:
        if isinstance(namespace, CacheNamespace):
            return namespace.value

        return str(namespace)

    def _increment_stat(
        self,
        operation: CacheOperation,
    ) -> None:
        field = self.STAT_FIELDS.get(
            operation
        )

        if not field:
            return

        try:
            client = redis_client.get_client()

            client.hincrby(
                cache_key_service.stats_key(),
                field,
                1,
            )

        except RedisError:
            logger.debug(
                "Could not update cache statistic %s.",
                field,
            )

    def _register_namespace(
        self,
        namespace: str,
    ) -> None:
        try:
            client = redis_client.get_client()

            client.sadd(
                (
                    f"{cache_key_service.ROOT_PREFIX}:"
                    f"{cache_key_service.VERSION}:"
                    "namespaces"
                ),
                namespace,
            )

        except RedisError:
            logger.debug(
                "Could not register cache namespace %s.",
                namespace,
            )

    def get(
        self,
        *,
        namespace: CacheNamespace | str,
        parts: list[Any],
    ) -> CacheGetResult:
        namespace_value = (
            self._namespace_value(namespace)
        )

        key = cache_key_service.build(
            namespace,
            *parts,
        )

        try:
            client = redis_client.get_client()

            raw_value = client.get(key)

            if raw_value is None:
                self._increment_stat(
                    CacheOperation.MISS
                )

                return CacheGetResult(
                    found=False,
                    key=key,
                    namespace=namespace_value,
                    value=None,
                    ttl_seconds=None,
                )

            ttl = int(client.ttl(key))

            value = (
                cache_serialization_service
                .deserialize(raw_value)
            )

            self._increment_stat(
                CacheOperation.HIT
            )

            return CacheGetResult(
                found=True,
                key=key,
                namespace=namespace_value,
                value=value,
                ttl_seconds=(
                    ttl
                    if ttl >= 0
                    else None
                ),
            )

        except (
            RedisError,
            ValueError,
            TypeError,
        ) as error:
            self._increment_stat(
                CacheOperation.ERROR
            )

            logger.warning(
                "Cache read failed for key %s: %s",
                key,
                error,
            )

            return CacheGetResult(
                found=False,
                key=key,
                namespace=namespace_value,
                value=None,
                ttl_seconds=None,
            )

    def set(
        self,
        *,
        namespace: CacheNamespace | str,
        parts: list[Any],
        value: Any,
        ttl_seconds: int | None = None,
        tags: list[str] | None = None,
    ) -> CacheSetResult:
        namespace_value = (
            self._namespace_value(namespace)
        )

        key = cache_key_service.build(
            namespace,
            *parts,
        )

        resolved_ttl = (
            ttl_seconds
            if ttl_seconds is not None
            else self.DEFAULT_TTL_SECONDS
        )

        tags = list(
            dict.fromkeys(tags or [])
        )

        try:
            serialized = (
                cache_serialization_service
                .serialize(value)
            )

            client = redis_client.get_client()

            pipeline = client.pipeline()

            if resolved_ttl > 0:
                pipeline.setex(
                    key,
                    resolved_ttl,
                    serialized,
                )
            else:
                pipeline.set(
                    key,
                    serialized,
                )

            for tag in tags:
                tag_key = (
                    cache_key_service.tag_key(tag)
                )

                pipeline.sadd(
                    tag_key,
                    key,
                )

                if resolved_ttl > 0:
                    pipeline.expire(
                        tag_key,
                        resolved_ttl + 300,
                    )

            pipeline.execute()

            self._register_namespace(
                namespace_value
            )

            self._increment_stat(
                CacheOperation.SET
            )

            return CacheSetResult(
                stored=True,
                key=key,
                namespace=namespace_value,
                ttl_seconds=(
                    resolved_ttl
                    if resolved_ttl > 0
                    else None
                ),
                tags=tags,
            )

        except (
            RedisError,
            ValueError,
            TypeError,
        ) as error:
            self._increment_stat(
                CacheOperation.ERROR
            )

            logger.warning(
                "Cache write failed for key %s: %s",
                key,
                error,
            )

            return CacheSetResult(
                stored=False,
                key=key,
                namespace=namespace_value,
                ttl_seconds=None,
                tags=tags,
            )

    def delete(
        self,
        *,
        namespace: CacheNamespace | str,
        parts: list[Any],
    ) -> CacheDeleteResult:
        key = cache_key_service.build(
            namespace,
            *parts,
        )

        return self.delete_keys(
            [key]
        )

    def delete_keys(
        self,
        keys: list[str],
    ) -> CacheDeleteResult:
        unique_keys = list(
            dict.fromkeys(keys)
        )

        if not unique_keys:
            return CacheDeleteResult(
                deleted=False,
                deleted_count=0,
                keys=[],
            )

        try:
            client = redis_client.get_client()

            deleted_count = int(
                client.delete(
                    *unique_keys
                )
            )

            self._increment_stat(
                CacheOperation.DELETE
            )

            return CacheDeleteResult(
                deleted=deleted_count > 0,
                deleted_count=deleted_count,
                keys=unique_keys,
            )

        except RedisError as error:
            self._increment_stat(
                CacheOperation.ERROR
            )

            logger.warning(
                "Cache delete failed: %s",
                error,
            )

            return CacheDeleteResult(
                deleted=False,
                deleted_count=0,
                keys=unique_keys,
            )

    def invalidate_tag(
        self,
        *,
        tag: str,
    ) -> CacheTagInvalidationResult:
        tag_key = cache_key_service.tag_key(
            tag
        )

        try:
            client = redis_client.get_client()

            raw_keys = client.smembers(
                tag_key
            )

            keys = [
                (
                    key.decode("utf-8")
                    if isinstance(key, bytes)
                    else str(key)
                )
                for key in raw_keys
            ]

            pipeline = client.pipeline()

            if keys:
                pipeline.delete(*keys)

            pipeline.delete(tag_key)
            results = pipeline.execute()

            deleted_count = (
                int(results[0])
                if keys and results
                else 0
            )

            self._increment_stat(
                CacheOperation.DELETE
            )

            return CacheTagInvalidationResult(
                tag=tag,
                deleted_count=deleted_count,
                keys=keys,
            )

        except RedisError as error:
            self._increment_stat(
                CacheOperation.ERROR
            )

            logger.warning(
                "Cache tag invalidation failed "
                "for %s: %s",
                tag,
                error,
            )

            return CacheTagInvalidationResult(
                tag=tag,
                deleted_count=0,
                keys=[],
            )

    def invalidate_namespace(
        self,
        *,
        namespace: CacheNamespace | str,
        scan_count: int = 500,
    ) -> CacheNamespaceInvalidationResult:
        namespace_value = (
            self._namespace_value(namespace)
        )

        pattern = (
            cache_key_service
            .namespace_pattern(namespace)
        )

        deleted_count = 0

        try:
            client = redis_client.get_client()

            keys_batch: list[str] = []

            for raw_key in client.scan_iter(
                match=pattern,
                count=scan_count,
            ):
                key = (
                    raw_key.decode("utf-8")
                    if isinstance(raw_key, bytes)
                    else str(raw_key)
                )

                keys_batch.append(key)

                if len(keys_batch) >= 500:
                    deleted_count += int(
                        client.delete(
                            *keys_batch
                        )
                    )

                    keys_batch.clear()

            if keys_batch:
                deleted_count += int(
                    client.delete(
                        *keys_batch
                    )
                )

            self._increment_stat(
                CacheOperation.DELETE
            )

            return (
                CacheNamespaceInvalidationResult(
                    namespace=namespace_value,
                    deleted_count=deleted_count,
                )
            )

        except RedisError as error:
            self._increment_stat(
                CacheOperation.ERROR
            )

            logger.warning(
                "Cache namespace invalidation "
                "failed for %s: %s",
                namespace_value,
                error,
            )

            return (
                CacheNamespaceInvalidationResult(
                    namespace=namespace_value,
                    deleted_count=0,
                )
            )

    def remember(
        self,
        *,
        namespace: CacheNamespace | str,
        parts: list[Any],
        loader: Callable[[], T],
        ttl_seconds: int | None = None,
        tags: list[str] | None = None,
    ) -> T:
        cached = self.get(
            namespace=namespace,
            parts=parts,
        )

        if cached.found:
            return cached.value

        value = loader()

        self.set(
            namespace=namespace,
            parts=parts,
            value=value,
            ttl_seconds=ttl_seconds,
            tags=tags,
        )

        return value

    def remember_optional(
        self,
        *,
        namespace: CacheNamespace | str,
        parts: list[Any],
        loader: Callable[[], T | None],
        ttl_seconds: int | None = None,
        negative_ttl_seconds: int = 30,
        tags: list[str] | None = None,
    ) -> T | None:
        cached = self.get(
            namespace=namespace,
            parts=parts,
        )

        if cached.found:
            return cached.value

        value = loader()

        self.set(
            namespace=namespace,
            parts=parts,
            value=value,
            ttl_seconds=(
                ttl_seconds
                if value is not None
                else negative_ttl_seconds
            ),
            tags=tags,
        )

        return value

    def acquire_lock(
        self,
        *,
        name: str,
        owner: str,
        ttl_seconds: int = 30,
    ) -> bool:
        key = cache_key_service.build(
            CacheNamespace.SYSTEM,
            "lock",
            name,
        )

        try:
            client = redis_client.get_client()

            return bool(
                client.set(
                    key,
                    owner,
                    ex=ttl_seconds,
                    nx=True,
                )
            )

        except RedisError as error:
            logger.warning(
                "Could not acquire distributed "
                "lock %s: %s",
                name,
                error,
            )

            return False

    def release_lock(
        self,
        *,
        name: str,
        owner: str,
    ) -> bool:
        key = cache_key_service.build(
            CacheNamespace.SYSTEM,
            "lock",
            name,
        )

        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """

        try:
            client = redis_client.get_client()

            result = client.eval(
                script,
                1,
                key,
                owner,
            )

            return bool(result)

        except RedisError as error:
            logger.warning(
                "Could not release distributed "
                "lock %s: %s",
                name,
                error,
            )

            return False

    def get_stats(
        self,
    ) -> CacheStatsResponse:
        hits = 0
        misses = 0
        sets = 0
        deletes = 0
        errors = 0
        namespaces: list[str] = []

        redis_available = redis_client.ping()

        if redis_available:
            try:
                client = redis_client.get_client()

                raw_stats = client.hgetall(
                    cache_key_service.stats_key()
                )

                decoded_stats = {
                    (
                        key.decode("utf-8")
                        if isinstance(key, bytes)
                        else str(key)
                    ): int(value)
                    for key, value
                    in raw_stats.items()
                }

                hits = decoded_stats.get(
                    "hits",
                    0,
                )

                misses = decoded_stats.get(
                    "misses",
                    0,
                )

                sets = decoded_stats.get(
                    "sets",
                    0,
                )

                deletes = decoded_stats.get(
                    "deletes",
                    0,
                )

                errors = decoded_stats.get(
                    "errors",
                    0,
                )

                namespace_key = (
                    f"{cache_key_service.ROOT_PREFIX}:"
                    f"{cache_key_service.VERSION}:"
                    "namespaces"
                )

                raw_namespaces = client.smembers(
                    namespace_key
                )

                namespaces = sorted(
                    [
                        (
                            value.decode("utf-8")
                            if isinstance(value, bytes)
                            else str(value)
                        )
                        for value
                        in raw_namespaces
                    ]
                )

            except RedisError as error:
                redis_available = False

                logger.warning(
                    "Could not read cache stats: %s",
                    error,
                )

        total_reads = hits + misses

        hit_rate = (
            hits / total_reads
            if total_reads > 0
            else 0.0
        )

        return CacheStatsResponse(
            redis_available=redis_available,
            hits=hits,
            misses=misses,
            sets=sets,
            deletes=deletes,
            errors=errors,
            hit_rate=round(
                hit_rate,
                4,
            ),
            tracked_namespaces=namespaces,
            generated_at=utc_now(),
        )


distributed_cache_service = (
    DistributedCacheService()
)