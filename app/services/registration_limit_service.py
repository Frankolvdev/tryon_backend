import hashlib
import logging
import threading
import time
from collections import defaultdict

from app.core.config import settings


logger = logging.getLogger(
    "app.registration_limits"
)


class RegistrationLimitService:
    WINDOW_SECONDS = 86400

    def __init__(
        self,
    ):
        self._fallback: dict[
            str,
            list[float],
        ] = defaultdict(list)

        self._lock = threading.Lock()

    def _hash_value(
        self,
        value: str,
    ) -> str:
        return hashlib.sha256(
            value.encode("utf-8")
        ).hexdigest()

    def _redis_client(
        self,
    ):
        try:
            import redis

            redis_url = getattr(
                settings,
                "REDIS_URL",
                "redis://127.0.0.1:6379/0",
            )

            client = redis.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )

            client.ping()

            return client

        except Exception:
            return None

    def _key(
        self,
        *,
        category: str,
        value: str,
    ) -> str:
        return (
            "security:registration:"
            f"{category}:"
            f"{self._hash_value(value)}"
        )

    def _check_redis(
        self,
        *,
        key: str,
        limit: int,
    ) -> None:
        client = self._redis_client()

        if client is None:
            raise RuntimeError(
                "Redis unavailable."
            )

        current = int(
            client.get(key) or 0
        )

        if current >= limit:
            raise PermissionError(
                "Registration limit reached."
            )

    def _increment_redis(
        self,
        *,
        key: str,
    ) -> None:
        client = self._redis_client()

        if client is None:
            raise RuntimeError(
                "Redis unavailable."
            )

        value = client.incr(key)

        if value == 1:
            client.expire(
                key,
                self.WINDOW_SECONDS,
            )

    def _check_fallback(
        self,
        *,
        key: str,
        limit: int,
    ) -> None:
        now = time.time()
        threshold = (
            now - self.WINDOW_SECONDS
        )

        with self._lock:
            self._fallback[key] = [
                timestamp
                for timestamp
                in self._fallback[key]
                if timestamp >= threshold
            ]

            if (
                len(self._fallback[key])
                >= limit
            ):
                raise PermissionError(
                    "Registration limit reached."
                )

    def _increment_fallback(
        self,
        *,
        key: str,
    ) -> None:
        with self._lock:
            self._fallback[key].append(
                time.time()
            )

    def check(
        self,
        *,
        ip_address: str | None,
        device_id: str | None,
        max_per_ip: int,
        max_per_device: int,
    ) -> None:
        values: list[
            tuple[str, str, int]
        ] = []

        if ip_address:
            values.append(
                (
                    "ip",
                    ip_address,
                    max_per_ip,
                )
            )

        if device_id:
            values.append(
                (
                    "device",
                    device_id,
                    max_per_device,
                )
            )

        for category, value, limit in values:
            key = self._key(
                category=category,
                value=value,
            )

            try:
                self._check_redis(
                    key=key,
                    limit=limit,
                )

            except PermissionError:
                raise

            except Exception:
                self._check_fallback(
                    key=key,
                    limit=limit,
                )

    def register_success(
        self,
        *,
        ip_address: str | None,
        device_id: str | None,
    ) -> None:
        values: list[
            tuple[str, str]
        ] = []

        if ip_address:
            values.append(
                ("ip", ip_address)
            )

        if device_id:
            values.append(
                ("device", device_id)
            )

        for category, value in values:
            key = self._key(
                category=category,
                value=value,
            )

            try:
                self._increment_redis(
                    key=key,
                )

            except Exception:
                self._increment_fallback(
                    key=key,
                )


registration_limit_service = (
    RegistrationLimitService()
)