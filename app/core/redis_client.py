from functools import lru_cache

from redis import Redis
from redis.connection import BlockingConnectionPool
from redis.exceptions import RedisError

from app.core.config import settings


class RedisClient:
    def __init__(self):
        self._client: Redis | None = None

    def _redis_url(self) -> str:
        configured_url = getattr(
            settings,
            "REDIS_URL",
            None,
        )

        if configured_url:
            return configured_url

        redis_host = getattr(
            settings,
            "REDIS_HOST",
            "127.0.0.1",
        )

        redis_port = getattr(
            settings,
            "REDIS_PORT",
            6379,
        )

        redis_db = getattr(
            settings,
            "REDIS_DB",
            0,
        )

        redis_password = getattr(
            settings,
            "REDIS_PASSWORD",
            None,
        )

        if redis_password:
            return (
                f"redis://:{redis_password}@"
                f"{redis_host}:{redis_port}/{redis_db}"
            )

        return (
            f"redis://{redis_host}:"
            f"{redis_port}/{redis_db}"
        )

    def get_client(self) -> Redis:
        if self._client is None:
            pool = BlockingConnectionPool.from_url(
                self._redis_url(),
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
                health_check_interval=30,
                max_connections=max(32, int(getattr(settings, "REDIS_MAX_CONNECTIONS", 256))),
                timeout=max(1, int(getattr(settings, "REDIS_POOL_WAIT_SECONDS", 5))),
            )
            self._client = Redis(connection_pool=pool)

        return self._client

    def ping(self) -> bool:
        try:
            return bool(self.get_client().ping())
        except RedisError:
            return False

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None


@lru_cache
def get_redis_client() -> RedisClient:
    return RedisClient()


redis_client = get_redis_client()