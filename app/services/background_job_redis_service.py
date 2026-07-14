import json
import logging
from typing import Any

from redis.exceptions import RedisError

from app.core.redis_client import redis_client


logger = logging.getLogger(__name__)


class BackgroundJobRedisService:
    SIGNAL_PREFIX = "background-jobs:signal"
    STATUS_PREFIX = "background-jobs:status"

    def _signal_key(
        self,
        queue_name: str,
    ) -> str:
        return (
            f"{self.SIGNAL_PREFIX}:"
            f"{queue_name}"
        )

    def _status_channel(
        self,
        public_id: str,
    ) -> str:
        return (
            f"{self.STATUS_PREFIX}:"
            f"{public_id}"
        )

    def notify_queue(
        self,
        *,
        queue_name: str,
        job_public_id: str | None = None,
    ) -> bool:
        try:
            client = redis_client.get_client()

            payload = json.dumps(
                {
                    "queue_name": queue_name,
                    "job_public_id": job_public_id,
                },
                ensure_ascii=False,
            )

            signal_key = self._signal_key(
                queue_name
            )

            pipeline = client.pipeline()

            pipeline.lpush(
                signal_key,
                payload,
            )

            # Redis is only a signal bus. We do not need to retain
            # thousands of duplicate wake-up messages.
            pipeline.ltrim(
                signal_key,
                0,
                999,
            )

            pipeline.expire(
                signal_key,
                86400,
            )

            pipeline.execute()

            return True

        except RedisError as error:
            logger.warning(
                "Could not publish queue signal for %s: %s",
                queue_name,
                error,
            )

            return False

    def wait_for_signal(
        self,
        *,
        queue_name: str,
        timeout_seconds: int = 10,
    ) -> dict[str, Any] | None:
        try:
            client = redis_client.get_client()

            result = client.brpop(
                self._signal_key(queue_name),
                timeout=timeout_seconds,
            )

            if not result:
                return None

            _, raw_payload = result

            parsed = json.loads(raw_payload)

            return (
                parsed
                if isinstance(parsed, dict)
                else None
            )

        except (
            RedisError,
            json.JSONDecodeError,
        ) as error:
            logger.warning(
                "Could not wait for queue signal %s: %s",
                queue_name,
                error,
            )

            return None

    def publish_status(
        self,
        *,
        public_id: str,
        status: str,
        progress: float,
        message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        try:
            client = redis_client.get_client()

            payload = json.dumps(
                {
                    "public_id": public_id,
                    "status": status,
                    "progress": progress,
                    "message": message,
                    "metadata": metadata or {},
                },
                ensure_ascii=False,
                default=str,
            )

            client.publish(
                self._status_channel(public_id),
                payload,
            )

            return True

        except RedisError as error:
            logger.warning(
                "Could not publish job status for %s: %s",
                public_id,
                error,
            )

            return False

    def ping(self) -> bool:
        return redis_client.ping()


background_job_redis_service = (
    BackgroundJobRedisService()
)