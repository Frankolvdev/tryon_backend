import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

from app.common.cache_enums import CacheNamespace
from app.services.distributed_cache_service import (
    distributed_cache_service,
)
from app.services.distributed_lock_service import (
    distributed_lock_service,
)


T = TypeVar("T")


class CacheStampedeService:
    def _jittered_ttl(
        self,
        ttl_seconds: int,
        jitter_ratio: float,
    ) -> int:
        if ttl_seconds <= 0:
            return ttl_seconds

        jitter = int(
            ttl_seconds
            * max(min(jitter_ratio, 0.5), 0.0)
        )

        if jitter <= 0:
            return ttl_seconds

        return max(
            ttl_seconds
            + random.randint(-jitter, jitter),
            1,
        )

    def remember(
        self,
        *,
        namespace: CacheNamespace | str,
        parts: list[Any],
        loader: Callable[[], T],
        ttl_seconds: int = 300,
        tags: list[str] | None = None,
        lock_ttl_seconds: int = 30,
        lock_wait_seconds: float = 2.0,
        poll_interval_seconds: float = 0.1,
        jitter_ratio: float = 0.1,
    ) -> T:
        cached = distributed_cache_service.get(
            namespace=namespace,
            parts=parts,
        )

        if cached.found:
            return cached.value

        lock_name = ":".join(
            [
                str(namespace),
                *[
                    str(part)
                    for part in parts
                ],
            ]
        )

        lock = distributed_lock_service.acquire(
            name=lock_name,
            ttl_seconds=lock_ttl_seconds,
            wait_timeout_seconds=0,
        )

        if lock.acquired:
            try:
                second_check = (
                    distributed_cache_service.get(
                        namespace=namespace,
                        parts=parts,
                    )
                )

                if second_check.found:
                    return second_check.value

                value = loader()

                distributed_cache_service.set(
                    namespace=namespace,
                    parts=parts,
                    value=value,
                    ttl_seconds=self._jittered_ttl(
                        ttl_seconds,
                        jitter_ratio,
                    ),
                    tags=tags,
                )

                return value

            finally:
                distributed_lock_service.release(
                    lock
                )

        deadline = (
            time.monotonic()
            + max(lock_wait_seconds, 0.0)
        )

        while time.monotonic() < deadline:
            time.sleep(
                max(poll_interval_seconds, 0.01)
            )

            cached = distributed_cache_service.get(
                namespace=namespace,
                parts=parts,
            )

            if cached.found:
                return cached.value

        value = loader()

        distributed_cache_service.set(
            namespace=namespace,
            parts=parts,
            value=value,
            ttl_seconds=self._jittered_ttl(
                ttl_seconds,
                jitter_ratio,
            ),
            tags=tags,
        )

        return value

    def remember_optional(
        self,
        *,
        namespace: CacheNamespace | str,
        parts: list[Any],
        loader: Callable[[], T | None],
        ttl_seconds: int = 300,
        negative_ttl_seconds: int = 30,
        tags: list[str] | None = None,
        lock_ttl_seconds: int = 30,
        lock_wait_seconds: float = 2.0,
        poll_interval_seconds: float = 0.1,
        jitter_ratio: float = 0.1,
    ) -> T | None:
        cached = distributed_cache_service.get(
            namespace=namespace,
            parts=parts,
        )

        if cached.found:
            return cached.value

        lock_name = ":".join(
            [
                str(namespace),
                "optional",
                *[
                    str(part)
                    for part in parts
                ],
            ]
        )

        lock = distributed_lock_service.acquire(
            name=lock_name,
            ttl_seconds=lock_ttl_seconds,
            wait_timeout_seconds=0,
        )

        if lock.acquired:
            try:
                second_check = (
                    distributed_cache_service.get(
                        namespace=namespace,
                        parts=parts,
                    )
                )

                if second_check.found:
                    return second_check.value

                value = loader()

                resolved_ttl = (
                    ttl_seconds
                    if value is not None
                    else negative_ttl_seconds
                )

                distributed_cache_service.set(
                    namespace=namespace,
                    parts=parts,
                    value=value,
                    ttl_seconds=self._jittered_ttl(
                        resolved_ttl,
                        jitter_ratio,
                    ),
                    tags=tags,
                )

                return value

            finally:
                distributed_lock_service.release(
                    lock
                )

        deadline = (
            time.monotonic()
            + max(lock_wait_seconds, 0.0)
        )

        while time.monotonic() < deadline:
            time.sleep(
                max(poll_interval_seconds, 0.01)
            )

            cached = distributed_cache_service.get(
                namespace=namespace,
                parts=parts,
            )

            if cached.found:
                return cached.value

        value = loader()

        resolved_ttl = (
            ttl_seconds
            if value is not None
            else negative_ttl_seconds
        )

        distributed_cache_service.set(
            namespace=namespace,
            parts=parts,
            value=value,
            ttl_seconds=self._jittered_ttl(
                resolved_ttl,
                jitter_ratio,
            ),
            tags=tags,
        )

        return value


cache_stampede_service = (
    CacheStampedeService()
)