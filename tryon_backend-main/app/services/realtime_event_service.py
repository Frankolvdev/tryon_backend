import json
import logging
from typing import Any

from redis.exceptions import RedisError

from app.core.redis_client import redis_client


logger = logging.getLogger(__name__)


class RealtimeEventService:
    ROOT_CHANNEL = "tryon-realtime"

    def _channel(
        self,
        topic: str,
        identifier: str | int | None = None,
    ) -> str:
        normalized_topic = (
            str(topic)
            .strip()
            .lower()
            .replace(" ", "-")
        )

        if identifier is None:
            return (
                f"{self.ROOT_CHANNEL}:"
                f"{normalized_topic}"
            )

        return (
            f"{self.ROOT_CHANNEL}:"
            f"{normalized_topic}:"
            f"{identifier}"
        )

    def publish(
        self,
        *,
        topic: str,
        identifier: str | int | None,
        event_type: str,
        data: dict[str, Any],
    ) -> bool:
        try:
            client = redis_client.get_client()

            payload = json.dumps(
                {
                    "topic": topic,
                    "identifier": identifier,
                    "event_type": event_type,
                    "data": data,
                },
                ensure_ascii=False,
                default=str,
            )

            client.publish(
                self._channel(
                    topic,
                    identifier,
                ),
                payload,
            )

            return True

        except RedisError as error:
            logger.warning(
                "Could not publish realtime event "
                "%s/%s: %s",
                topic,
                identifier,
                error,
            )

            return False

    def publish_job_progress(
        self,
        *,
        public_id: str,
        job_id: int,
        status: str,
        progress: float,
        message: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        return self.publish(
            topic="background-job",
            identifier=public_id,
            event_type="progress",
            data={
                "job_id": job_id,
                "public_id": public_id,
                "status": status,
                "progress": progress,
                "message": message,
                "metadata": metadata or {},
            },
        )

    def publish_tryon_update(
        self,
        *,
        tryon_job_id: int,
        status: str,
        data: dict[str, Any] | None = None,
    ) -> bool:
        return self.publish(
            topic="tryon-job",
            identifier=tryon_job_id,
            event_type="status_changed",
            data={
                "tryon_job_id": tryon_job_id,
                "status": status,
                **(data or {}),
            },
        )

    def publish_user_notification(
        self,
        *,
        user_id: int,
        event_type: str,
        data: dict[str, Any],
    ) -> bool:
        return self.publish(
            topic="user",
            identifier=user_id,
            event_type=event_type,
            data=data,
        )


realtime_event_service = RealtimeEventService()