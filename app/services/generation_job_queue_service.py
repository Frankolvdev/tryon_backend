from __future__ import annotations

import json
import logging
import threading
from collections import deque
from typing import Any
from uuid import UUID

from redis.exceptions import RedisError

from app.common.generation_module_enums import GenerationExecutionEngine
from app.core.redis_client import redis_client

logger = logging.getLogger(__name__)


class GenerationJobQueueService:
    """Durable provider-aware queue for generation-module executions.

    Redis is the normal queue backend. A small process-local fallback keeps
    development usable when Redis is temporarily unavailable, but durable
    recovery requires Redis and PostgreSQL.
    """

    PREFIX = "generation-jobs"

    def __init__(self) -> None:
        self._fallback: dict[str, deque[str]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def queue_name(engine: GenerationExecutionEngine | str) -> str:
        value = engine.value if isinstance(engine, GenerationExecutionEngine) else str(engine)
        if value == GenerationExecutionEngine.LOCAL_DOCKER.value:
            return "local"
        if value == GenerationExecutionEngine.RUNPOD_SERVERLESS.value:
            return "runpod"
        return "simulated"

    def _queue_key(self, queue_name: str) -> str:
        return f"{self.PREFIX}:queue:{queue_name}"

    def _dedupe_key(self, queue_name: str) -> str:
        return f"{self.PREFIX}:queued:{queue_name}"

    def enqueue(self, execution_id: UUID | str, *, engine: GenerationExecutionEngine | str) -> str:
        queue_name = self.queue_name(engine)
        value = str(execution_id)
        try:
            client = redis_client.get_client()
            pipeline = client.pipeline()
            pipeline.sadd(self._dedupe_key(queue_name), value)
            added, = pipeline.execute()
            if added:
                client.rpush(self._queue_key(queue_name), value)
            return queue_name
        except RedisError as exc:
            logger.warning("Redis generation queue unavailable; using in-memory fallback: %s", exc)
            with self._lock:
                queue = self._fallback.setdefault(queue_name, deque())
                if value not in queue:
                    queue.append(value)
            return queue_name

    def dequeue(self, queue_name: str, *, timeout_seconds: int = 2) -> str | None:
        try:
            client = redis_client.get_client()
            result = client.blpop(self._queue_key(queue_name), timeout=max(1, timeout_seconds))
            if not result:
                return None
            _, value = result
            client.srem(self._dedupe_key(queue_name), value)
            return str(value)
        except RedisError as exc:
            logger.warning("Redis generation dequeue unavailable; using in-memory fallback: %s", exc)
            with self._lock:
                queue = self._fallback.setdefault(queue_name, deque())
                return queue.popleft() if queue else None

    def remove(self, execution_id: UUID | str, *, engine: GenerationExecutionEngine | str) -> None:
        queue_name = self.queue_name(engine)
        value = str(execution_id)
        try:
            client = redis_client.get_client()
            pipeline = client.pipeline()
            pipeline.lrem(self._queue_key(queue_name), 0, value)
            pipeline.srem(self._dedupe_key(queue_name), value)
            pipeline.execute()
        except RedisError:
            pass
        with self._lock:
            queue = self._fallback.setdefault(queue_name, deque())
            self._fallback[queue_name] = deque(item for item in queue if item != value)

    def position(self, execution_id: UUID | str, *, engine: GenerationExecutionEngine | str) -> int | None:
        queue_name = self.queue_name(engine)
        value = str(execution_id)
        try:
            items = redis_client.get_client().lrange(self._queue_key(queue_name), 0, -1)
            return items.index(value) + 1 if value in items else None
        except RedisError:
            with self._lock:
                items = list(self._fallback.setdefault(queue_name, deque()))
                return items.index(value) + 1 if value in items else None

    def depths(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for name in ("local", "runpod", "simulated"):
            try:
                result[name] = int(redis_client.get_client().llen(self._queue_key(name)))
            except RedisError:
                with self._lock:
                    result[name] = len(self._fallback.setdefault(name, deque()))
        return result

    def ping(self) -> bool:
        return redis_client.ping()


generation_job_queue_service = GenerationJobQueueService()
