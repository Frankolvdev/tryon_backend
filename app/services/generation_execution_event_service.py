from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import AsyncIterator

import redis.asyncio as async_redis
from redis.exceptions import RedisError

from app.core.redis_client import redis_client
from app.schemas.generation_module_runtime import GenerationModuleExecutionResponse


@dataclass(eq=False)
class _LocalSubscriber:
    user_id: int
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[dict]


class GenerationExecutionEventService:
    """Best-effort realtime fanout for generation execution state changes.

    Durable execution state remains in SQL and is always authoritative. Redis is
    used only as a cross-process notification bus. Local subscribers are notified
    immediately even when Redis is unavailable; clients can fall back to the
    existing status endpoints whenever cross-process realtime is unavailable.
    """

    CHANNEL_PREFIX = "tryon:generation-executions:user:"
    PATTERN = f"{CHANNEL_PREFIX}*"
    HEARTBEAT_SECONDS = 15.0

    def __init__(self) -> None:
        self._instance_id = f"{os.getpid()}-{uuid.uuid4().hex}"
        self._subscribers: dict[int, set[_LocalSubscriber]] = defaultdict(set)
        self._subscribers_lock = threading.Lock()
        self._publish_queue: queue.Queue[tuple[str, str]] = queue.Queue(maxsize=4096)
        self._publisher_started = False
        self._publisher_lock = threading.Lock()
        self._listener_tasks: dict[int, asyncio.Task] = {}
        self._redis_ready_by_loop: dict[int, bool] = {}

    @staticmethod
    def _event_payload(execution: GenerationModuleExecutionResponse, *, origin: str) -> dict:
        return {
            "type": "execution",
            "origin": origin,
            "execution": {
                "id": str(execution.id),
                "module_id": execution.module_id,
                "module_key": execution.module_key,
                "status": execution.status,
                "progress": execution.progress,
                "cancel_requested": execution.cancel_requested,
                "provider_status": execution.provider_status,
                "started_at": execution.started_at.isoformat() if execution.started_at else None,
                "finished_at": execution.finished_at.isoformat() if execution.finished_at else None,
                "duration_ms": execution.duration_ms,
                "queue_name": execution.queue_name,
                "queue_position": execution.queue_position,
                "heartbeat_at": execution.heartbeat_at.isoformat() if execution.heartbeat_at else None,
                "recovery_count": execution.recovery_count,
                "recovered_at": execution.recovered_at.isoformat() if execution.recovered_at else None,
            },
        }

    def publish(self, execution: GenerationModuleExecutionResponse) -> None:
        user_id = execution.user_id
        if user_id is None:
            return
        payload = self._event_payload(execution, origin=self._instance_id)
        self._fanout_local(user_id, payload)
        self._ensure_publisher_thread()
        try:
            self._publish_queue.put_nowait((f"{self.CHANNEL_PREFIX}{user_id}", json.dumps(payload, separators=(",", ":"))))
        except queue.Full:
            # Realtime notifications are intentionally lossy under pressure. SQL
            # remains authoritative and the client reconciliation fallback repairs
            # any missed update without slowing the generation runtime.
            pass

    def _ensure_publisher_thread(self) -> None:
        if self._publisher_started:
            return
        with self._publisher_lock:
            if self._publisher_started:
                return
            thread = threading.Thread(target=self._publisher_worker, name="generation-sse-publisher", daemon=True)
            thread.start()
            self._publisher_started = True

    def _publisher_worker(self) -> None:
        while True:
            channel, payload = self._publish_queue.get()
            try:
                redis_client.get_client().publish(channel, payload)
            except RedisError:
                # Never block/fail generation persistence because realtime transport
                # is unavailable. Connected clients will use polling fallback.
                pass
            except Exception:
                pass
            finally:
                self._publish_queue.task_done()

    def _fanout_local(self, user_id: int, payload: dict) -> None:
        with self._subscribers_lock:
            subscribers = tuple(self._subscribers.get(user_id, ()))
        for subscriber in subscribers:
            def deliver(target=subscriber, item=payload):
                try:
                    if target.queue.full():
                        target.queue.get_nowait()
                    target.queue.put_nowait(item)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass
            try:
                subscriber.loop.call_soon_threadsafe(deliver)
            except RuntimeError:
                pass

    def _broadcast_transport(self, loop_id: int, ready: bool) -> None:
        previous = self._redis_ready_by_loop.get(loop_id)
        self._redis_ready_by_loop[loop_id] = ready
        if previous is ready:
            return
        with self._subscribers_lock:
            subscribers = tuple(sub for values in self._subscribers.values() for sub in values if id(sub.loop) == loop_id)
        payload = {"type": "transport", "cross_process": ready}
        for subscriber in subscribers:
            try:
                subscriber.queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    def _ensure_listener(self, loop: asyncio.AbstractEventLoop) -> None:
        loop_id = id(loop)
        task = self._listener_tasks.get(loop_id)
        if task and not task.done():
            return
        self._listener_tasks[loop_id] = loop.create_task(self._redis_listener(loop, loop_id))

    async def _redis_listener(self, loop: asyncio.AbstractEventLoop, loop_id: int) -> None:
        backoff = 1.0
        while True:
            client = None
            pubsub = None
            try:
                client = async_redis.Redis.from_url(
                    redis_client._redis_url(),
                    decode_responses=True,
                    socket_connect_timeout=1,
                    health_check_interval=30,
                )
                pubsub = client.pubsub()
                await pubsub.psubscribe(self.PATTERN)
                self._broadcast_transport(loop_id, True)
                backoff = 1.0
                async for message in pubsub.listen():
                    if message.get("type") != "pmessage":
                        continue
                    raw = message.get("data")
                    if not isinstance(raw, str):
                        continue
                    try:
                        payload = json.loads(raw)
                        if payload.get("origin") == self._instance_id:
                            continue
                        channel = str(message.get("channel") or "")
                        user_id = int(channel.rsplit(":", 1)[-1])
                    except (ValueError, TypeError, json.JSONDecodeError):
                        continue
                    self._fanout_local(user_id, payload)
            except asyncio.CancelledError:
                raise
            except Exception:
                self._broadcast_transport(loop_id, False)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, 15.0)
            finally:
                if pubsub is not None:
                    try:
                        await pubsub.close()
                    except Exception:
                        pass
                if client is not None:
                    try:
                        await client.close()
                    except Exception:
                        pass

    async def stream(self, user_id: int) -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        subscriber = _LocalSubscriber(user_id=user_id, loop=loop, queue=asyncio.Queue(maxsize=64))
        with self._subscribers_lock:
            self._subscribers[user_id].add(subscriber)
        self._ensure_listener(loop)
        loop_id = id(loop)
        try:
            yield self._encode_sse({"type": "transport", "cross_process": self._redis_ready_by_loop.get(loop_id, False)})
            while True:
                try:
                    payload = await asyncio.wait_for(subscriber.queue.get(), timeout=self.HEARTBEAT_SECONDS)
                    yield self._encode_sse(payload)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            with self._subscribers_lock:
                values = self._subscribers.get(user_id)
                if values is not None:
                    values.discard(subscriber)
                    if not values:
                        self._subscribers.pop(user_id, None)

    @staticmethod
    def _encode_sse(payload: dict) -> str:
        event_name = "execution" if payload.get("type") == "execution" else "transport"
        return f"event: {event_name}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


generation_execution_event_service = GenerationExecutionEventService()
