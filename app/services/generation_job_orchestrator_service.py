from __future__ import annotations

import logging
import threading
from uuid import UUID

from app.common.generation_module_enums import GenerationExecutionEngine
from app.core.config import settings
from app.db.database import SessionLocal
from app.services.generation_job_queue_service import generation_job_queue_service
from app.services.generation_module_execution_store_service import generation_module_execution_store_service
from app.services.generation_module_service import generation_module_service

logger = logging.getLogger(__name__)


class GenerationJobOrchestratorService:
    """Owns provider workers while RunPod owns its remote GPU orchestration."""

    def __init__(self) -> None:
        self._runtime = None
        self._threads: list[threading.Thread] = []
        self._stop = threading.Event()
        self._started = False
        self._lock = threading.Lock()

    def bind(self, runtime) -> None:
        self._runtime = runtime

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            self._stop.clear()
            specs = [
                ("local", max(1, int(settings.GENERATION_LOCAL_WORKERS))),
                ("runpod", max(1, int(settings.GENERATION_RUNPOD_DISPATCH_WORKERS))),
                ("simulated", max(1, int(settings.GENERATION_SIMULATED_WORKERS))),
            ]
            for queue_name, count in specs:
                for index in range(count):
                    thread = threading.Thread(
                        target=self._worker_loop,
                        args=(queue_name,),
                        name=f"generation-{queue_name}-{index + 1}",
                        daemon=True,
                    )
                    thread.start()
                    self._threads.append(thread)
        self.recover_pending()

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=3)
        self._threads.clear()
        self._started = False

    def submit(self, execution_id: UUID, *, engine: GenerationExecutionEngine) -> str:
        self.start()
        return generation_job_queue_service.enqueue(execution_id, engine=engine)

    def recover_pending(self) -> None:
        items, _ = generation_module_execution_store_service.list(skip=0, limit=10000)
        for item in items:
            if item.status == "queued":
                generation_job_queue_service.enqueue(item.id, engine=item.engine)
            elif item.status == "running":
                # The previous process cannot safely own a local/submitted call anymore.
                # Requeue it and preserve a clear recovery trace. Provider adapters are
                # idempotency-aware through the execution id payload where supported.
                item.status = "queued"
                item.progress = min(item.progress, 5)
                item.logs.append(self._runtime.recovery_log())
                generation_module_execution_store_service.save(item)
                generation_job_queue_service.enqueue(item.id, engine=item.engine)

    def _worker_loop(self, queue_name: str) -> None:
        while not self._stop.is_set():
            raw_id = generation_job_queue_service.dequeue(
                queue_name,
                timeout_seconds=int(settings.GENERATION_QUEUE_BLOCK_SECONDS),
            )
            if not raw_id:
                continue
            try:
                execution_id = UUID(raw_id)
                current = generation_module_execution_store_service.get(execution_id)
                if current is None or current.status != "queued" or current.cancel_requested:
                    continue
                db = SessionLocal()
                try:
                    module = generation_module_service.get_response(db, module_id=current.module_id)
                    self._runtime.attach_persisted(current)
                    self._runtime._run(execution_id, module.model_dump(mode="python"))
                finally:
                    db.close()
            except Exception:
                logger.exception("Generation worker failed while handling %s", raw_id)

    def status(self) -> dict:
        return {
            "redis_available": generation_job_queue_service.ping(),
            "queue_depths": generation_job_queue_service.depths(),
            "workers": {
                "local": max(1, int(settings.GENERATION_LOCAL_WORKERS)),
                "runpod_dispatch": max(1, int(settings.GENERATION_RUNPOD_DISPATCH_WORKERS)),
                "simulated": max(1, int(settings.GENERATION_SIMULATED_WORKERS)),
            },
        }


generation_job_orchestrator_service = GenerationJobOrchestratorService()
