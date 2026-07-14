import secrets
import time
from dataclasses import dataclass

from redis.exceptions import RedisError

from app.common.cache_enums import CacheNamespace
from app.services.cache_key_service import cache_key_service
from app.core.redis_client import redis_client


@dataclass
class DistributedLock:
    name: str
    owner: str
    acquired: bool
    ttl_seconds: int


class DistributedLockService:
    RELEASE_SCRIPT = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """

    EXTEND_SCRIPT = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("expire", KEYS[1], ARGV[2])
    else
        return 0
    end
    """

    def _key(
        self,
        name: str,
    ) -> str:
        return cache_key_service.build(
            CacheNamespace.SYSTEM,
            "distributed-lock",
            name,
        )

    def acquire(
        self,
        *,
        name: str,
        ttl_seconds: int = 30,
        wait_timeout_seconds: float = 0.0,
        retry_interval_seconds: float = 0.1,
    ) -> DistributedLock:
        owner = secrets.token_urlsafe(32)
        deadline = (
            time.monotonic()
            + max(wait_timeout_seconds, 0.0)
        )

        while True:
            try:
                client = redis_client.get_client()

                acquired = bool(
                    client.set(
                        self._key(name),
                        owner,
                        ex=max(ttl_seconds, 1),
                        nx=True,
                    )
                )

                if acquired:
                    return DistributedLock(
                        name=name,
                        owner=owner,
                        acquired=True,
                        ttl_seconds=ttl_seconds,
                    )

            except RedisError:
                return DistributedLock(
                    name=name,
                    owner=owner,
                    acquired=False,
                    ttl_seconds=ttl_seconds,
                )

            if time.monotonic() >= deadline:
                return DistributedLock(
                    name=name,
                    owner=owner,
                    acquired=False,
                    ttl_seconds=ttl_seconds,
                )

            time.sleep(
                max(retry_interval_seconds, 0.01)
            )

    def release(
        self,
        lock: DistributedLock,
    ) -> bool:
        if not lock.acquired:
            return False

        try:
            client = redis_client.get_client()

            result = client.eval(
                self.RELEASE_SCRIPT,
                1,
                self._key(lock.name),
                lock.owner,
            )

            return bool(result)

        except RedisError:
            return False

    def extend(
        self,
        lock: DistributedLock,
        *,
        ttl_seconds: int,
    ) -> bool:
        if not lock.acquired:
            return False

        try:
            client = redis_client.get_client()

            result = client.eval(
                self.EXTEND_SCRIPT,
                1,
                self._key(lock.name),
                lock.owner,
                max(ttl_seconds, 1),
            )

            if result:
                lock.ttl_seconds = ttl_seconds

            return bool(result)

        except RedisError:
            return False


distributed_lock_service = (
    DistributedLockService()
)