import hashlib
import math
import time
from datetime import timedelta
from typing import Any

from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.common.rate_limit_enums import (
    RateLimitAction,
    RateLimitAlgorithm,
    RateLimitScope,
)
from app.common.time import utc_now
from app.core.redis_client import redis_client
from app.models.rate_limit_policy import RateLimitPolicy
from app.schemas.rate_limit_runtime import (
    RateLimitCheckResult,
    RateLimitIdentity,
)


class RateLimitEngineService:
    SLIDING_WINDOW_SCRIPT = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local window_start = tonumber(ARGV[2])
    local member = ARGV[3]
    local ttl = tonumber(ARGV[4])

    redis.call('ZREMRANGEBYSCORE', key, 0, window_start)
    redis.call('ZADD', key, now, member)

    local count = redis.call('ZCARD', key)
    redis.call('EXPIRE', key, ttl)

    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local oldest_score = now

    if oldest[2] ~= nil then
        oldest_score = tonumber(oldest[2])
    end

    return {count, oldest_score}
    """

    def _hash(self, value: str) -> str:
        return hashlib.sha256(
            value.encode("utf-8")
        ).hexdigest()

    def _identifier_for_policy(
        self,
        *,
        policy: RateLimitPolicy,
        identity: RateLimitIdentity,
        route: str,
    ) -> str:
        if policy.scope == RateLimitScope.USER.value:
            if identity.user_id is not None:
                return f"user:{identity.user_id}"

            return (
                f"ip:{identity.ip_address or 'unknown'}"
            )

        if policy.scope == RateLimitScope.API_KEY.value:
            if identity.api_key_id is not None:
                return f"api-key:{identity.api_key_id}"

            if identity.api_key_hash:
                return (
                    f"api-key-hash:"
                    f"{self._hash(identity.api_key_hash)}"
                )

            return (
                f"ip:{identity.ip_address or 'unknown'}"
            )

        if policy.scope == RateLimitScope.GLOBAL.value:
            return "global"

        if policy.scope == RateLimitScope.ENDPOINT.value:
            return (
                f"endpoint:{self._hash(route)}:"
                f"ip:{identity.ip_address or 'unknown'}"
            )

        return f"ip:{identity.ip_address or 'unknown'}"

    def _counter_key(
        self,
        *,
        policy: RateLimitPolicy,
        identifier: str,
    ) -> str:
        return (
            f"rate-limit:counter:"
            f"{policy.key}:"
            f"{self._hash(identifier)}"
        )

    def _block_key(
        self,
        *,
        policy: RateLimitPolicy,
        identifier: str,
    ) -> str:
        return (
            f"rate-limit:block:"
            f"{policy.key}:"
            f"{self._hash(identifier)}"
        )

    def _effective_limit(
        self,
        policy: RateLimitPolicy,
    ) -> int:
        if policy.burst_limit is not None:
            return max(
                policy.request_limit,
                policy.burst_limit,
            )

        return policy.request_limit

    def _is_temporarily_blocked(
        self,
        *,
        policy: RateLimitPolicy,
        identifier: str,
    ) -> tuple[bool, int]:
        client = redis_client.get_client()

        block_key = self._block_key(
            policy=policy,
            identifier=identifier,
        )

        ttl = client.ttl(block_key)

        if ttl is None or ttl <= 0:
            return False, 0

        return True, int(ttl)

    def _apply_temporary_block(
        self,
        *,
        policy: RateLimitPolicy,
        identifier: str,
    ) -> int:
        if policy.block_seconds <= 0:
            return 0

        client = redis_client.get_client()

        block_key = self._block_key(
            policy=policy,
            identifier=identifier,
        )

        client.set(
            block_key,
            "1",
            ex=policy.block_seconds,
        )

        return policy.block_seconds

    def _fixed_window(
        self,
        *,
        policy: RateLimitPolicy,
        identifier: str,
    ) -> tuple[int, int]:
        client = redis_client.get_client()
        now_seconds = int(time.time())

        window_number = (
            now_seconds // policy.window_seconds
        )

        key = (
            f"{self._counter_key(policy=policy, identifier=identifier)}:"
            f"{window_number}"
        )

        pipeline = client.pipeline()
        pipeline.incr(key)
        pipeline.ttl(key)

        count, ttl = pipeline.execute()

        if ttl is None or ttl < 0:
            client.expire(
                key,
                policy.window_seconds + 1,
            )
            ttl = policy.window_seconds

        return int(count), max(int(ttl), 1)

    def _sliding_window(
        self,
        *,
        policy: RateLimitPolicy,
        identifier: str,
    ) -> tuple[int, int]:
        client = redis_client.get_client()

        now_ms = int(time.time() * 1000)
        window_ms = policy.window_seconds * 1000
        window_start = now_ms - window_ms

        unique_member = (
            f"{now_ms}:"
            f"{time.perf_counter_ns()}"
        )

        key = self._counter_key(
            policy=policy,
            identifier=identifier,
        )

        result = client.eval(
            self.SLIDING_WINDOW_SCRIPT,
            1,
            key,
            now_ms,
            window_start,
            unique_member,
            policy.window_seconds + 2,
        )

        count = int(result[0])
        oldest_score = int(result[1])

        reset_in_ms = max(
            1,
            oldest_score + window_ms - now_ms,
        )

        retry_after = max(
            1,
            math.ceil(reset_in_ms / 1000),
        )

        return count, retry_after

    def _fallback_result(
        self,
        *,
        policy: RateLimitPolicy,
        identifier: str,
        error: Exception,
    ) -> RateLimitCheckResult:
        now = utc_now()

        return RateLimitCheckResult(
            allowed=True,
            action=RateLimitAction.ALLOW,
            policy_id=policy.id,
            policy_key=policy.key,
            identifier=identifier,
            request_count=0,
            request_limit=self._effective_limit(policy),
            remaining=self._effective_limit(policy),
            window_seconds=policy.window_seconds,
            reset_at=now + timedelta(
                seconds=policy.window_seconds
            ),
            retry_after_seconds=0,
            blocked=False,
            blocked_until=None,
            redis_available=False,
            fallback_used=True,
            metadata={
                "fallback_mode": "fail_open",
                "error": str(error),
            },
        )

    def check(
        self,
        db: Session,
        *,
        policy: RateLimitPolicy,
        identity: RateLimitIdentity,
        route: str,
    ) -> RateLimitCheckResult:
        del db

        identifier = self._identifier_for_policy(
            policy=policy,
            identity=identity,
            route=route,
        )

        now = utc_now()
        effective_limit = self._effective_limit(
            policy
        )

        try:
            blocked, block_ttl = (
                self._is_temporarily_blocked(
                    policy=policy,
                    identifier=identifier,
                )
            )

            if blocked:
                blocked_until = now + timedelta(
                    seconds=block_ttl
                )

                return RateLimitCheckResult(
                    allowed=False,
                    action=RateLimitAction.BLOCK,
                    policy_id=policy.id,
                    policy_key=policy.key,
                    identifier=identifier,
                    request_count=effective_limit + 1,
                    request_limit=effective_limit,
                    remaining=0,
                    window_seconds=policy.window_seconds,
                    reset_at=blocked_until,
                    retry_after_seconds=block_ttl,
                    blocked=True,
                    blocked_until=blocked_until,
                    redis_available=True,
                    fallback_used=False,
                    metadata={
                        "reason": "temporary_block",
                    },
                )

            if (
                policy.algorithm
                == RateLimitAlgorithm.FIXED_WINDOW.value
            ):
                request_count, retry_after = (
                    self._fixed_window(
                        policy=policy,
                        identifier=identifier,
                    )
                )
            else:
                request_count, retry_after = (
                    self._sliding_window(
                        policy=policy,
                        identifier=identifier,
                    )
                )

            exceeded = request_count > effective_limit

            block_ttl = 0

            if exceeded and policy.block_seconds > 0:
                block_ttl = (
                    self._apply_temporary_block(
                        policy=policy,
                        identifier=identifier,
                    )
                )

            if block_ttl > 0:
                retry_after = block_ttl

            remaining = max(
                effective_limit - request_count,
                0,
            )

            blocked_until = (
                now + timedelta(seconds=retry_after)
                if exceeded and block_ttl > 0
                else None
            )

            return RateLimitCheckResult(
                allowed=not exceeded,
                action=(
                    RateLimitAction.BLOCK
                    if exceeded and block_ttl > 0
                    else (
                        RateLimitAction.THROTTLE
                        if exceeded
                        else RateLimitAction.ALLOW
                    )
                ),
                policy_id=policy.id,
                policy_key=policy.key,
                identifier=identifier,
                request_count=request_count,
                request_limit=effective_limit,
                remaining=remaining,
                window_seconds=policy.window_seconds,
                reset_at=now + timedelta(
                    seconds=retry_after
                ),
                retry_after_seconds=(
                    retry_after
                    if exceeded
                    else 0
                ),
                blocked=(
                    exceeded and block_ttl > 0
                ),
                blocked_until=blocked_until,
                redis_available=True,
                fallback_used=False,
                metadata={
                    "algorithm": policy.algorithm,
                    "base_request_limit": (
                        policy.request_limit
                    ),
                    "burst_limit": policy.burst_limit,
                },
            )

        except RedisError as error:
            return self._fallback_result(
                policy=policy,
                identifier=identifier,
                error=error,
            )
        except Exception as error:
            return self._fallback_result(
                policy=policy,
                identifier=identifier,
                error=error,
            )

    def reset(
        self,
        *,
        policy: RateLimitPolicy,
        identifier: str,
    ) -> None:
        client = redis_client.get_client()

        counter_pattern = (
            f"{self._counter_key(policy=policy, identifier=identifier)}*"
        )

        block_key = self._block_key(
            policy=policy,
            identifier=identifier,
        )

        keys = list(
            client.scan_iter(
                match=counter_pattern,
                count=100,
            )
        )

        if block_key:
            keys.append(block_key)

        if keys:
            client.delete(*keys)

    def headers(
        self,
        *,
        result: RateLimitCheckResult,
    ) -> dict[str, str]:
        headers = {
            "X-RateLimit-Limit": str(
                result.request_limit
            ),
            "X-RateLimit-Remaining": str(
                result.remaining
            ),
            "X-RateLimit-Reset": str(
                int(result.reset_at.timestamp())
            ),
            "X-RateLimit-Policy": (
                result.policy_key or ""
            ),
        }

        if result.retry_after_seconds > 0:
            headers["Retry-After"] = str(
                result.retry_after_seconds
            )

        return headers


rate_limit_engine_service = RateLimitEngineService()