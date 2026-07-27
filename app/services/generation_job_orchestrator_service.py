from __future__ import annotations

import logging
import threading
from uuid import UUID

from app.common.generation_module_enums import GenerationExecutionEngine
from app.common.time import utc_now
from app.core.config import settings
from app.db.database import SessionLocal
from app.schemas.generation_module_runtime import GenerationModuleExecutionLog
from app.services.generation_job_queue_service import generation_job_queue_service
from app.services.ai_engine_settings_service import ai_engine_settings_service
from app.services.generation_module_execution_store_service import generation_module_execution_store_service
from app.services.generation_module_service import generation_module_service

logger = logging.getLogger(__name__)


class GenerationJobOrchestratorService:
    """Owns provider workers while remote providers own GPU orchestration."""

    def __init__(self) -> None:
        self._runtime = None
        self._threads: list[threading.Thread] = []
        self._stop = threading.Event()
        self._started = False
        self._lock = threading.Lock()
        self._runtime_settings = None

    def bind(self, runtime) -> None:
        self._runtime = runtime

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            self._stop.clear()
            db = SessionLocal()
            try:
                self._runtime_settings = ai_engine_settings_service.get(db)
            finally:
                db.close()
            runpod_parallelism = min(
                self._runtime_settings.runpod_dispatch_workers,
                self._runtime_settings.runpod_max_in_flight,
            )
            specs = [
                ("local", self._runtime_settings.local_parallel_executions),
                ("runpod", runpod_parallelism),
                ("modal", max(1, int(self._runtime_settings.modal_max_containers) * int(self._runtime_settings.modal_concurrency))),
                ("beam", 5),
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
                item.status = "queued"
                item.progress = min(item.progress, 5)
                item.logs.append(self._runtime.recovery_log())
                generation_module_execution_store_service.save(item)
                generation_job_queue_service.enqueue(item.id, engine=item.engine)

    def _fail_orphaned_job(self, execution_id: UUID | None, error: Exception) -> None:
        if execution_id is None:
            return
        current = generation_module_execution_store_service.get(execution_id)
        if current is None or current.status != "queued":
            return
        current.status = "failed"
        current.error = f"Generation worker could not start the execution: {error}"
        current.finished_at = utc_now()
        current.provider_status = "DISPATCH_FAILED"
        current.logs.append(
            GenerationModuleExecutionLog(
                timestamp=current.finished_at,
                level="error",
                message=current.error,
            )
        )
        generation_module_execution_store_service.save(current)

    def _worker_loop(self, queue_name: str) -> None:
        while not self._stop.is_set():
            raw_id = generation_job_queue_service.dequeue(
                queue_name,
                timeout_seconds=int(
                    self._runtime_settings.queue_block_seconds
                    if self._runtime_settings
                    else settings.GENERATION_QUEUE_BLOCK_SECONDS
                ),
            )
            if not raw_id:
                continue
            execution_id: UUID | None = None
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
            except Exception as exc:
                logger.exception("Generation worker failed while handling %s", raw_id)
                self._fail_orphaned_job(execution_id, exc)

    def status(self) -> dict:
        return {
            "redis_available": generation_job_queue_service.ping(),
            "queue_depths": generation_job_queue_service.depths(),
            "workers": {
                "local": (
                    self._runtime_settings.local_parallel_executions
                    if self._runtime_settings
                    else max(1, int(settings.GENERATION_LOCAL_WORKERS))
                ),
                "runpod_dispatch": (
                    self._runtime_settings.effective_runpod_parallelism
                    if self._runtime_settings
                    else max(1, int(settings.GENERATION_RUNPOD_DISPATCH_WORKERS))
                ),
                "modal_dispatch": (
                    max(1, int(self._runtime_settings.modal_max_containers) * int(self._runtime_settings.modal_concurrency))
                    if self._runtime_settings
                    else max(1, int(settings.GENERATION_MODAL_DISPATCH_WORKERS))
                ),
                "beam_dispatch": 5,
                "simulated": max(1, int(settings.GENERATION_SIMULATED_WORKERS)),
            },
            "limits": {
                "runpod_max_in_flight": (
                    self._runtime_settings.runpod_max_in_flight
                    if self._runtime_settings
                    else max(1, int(settings.GENERATION_RUNPOD_MAX_IN_FLIGHT))
                ),
            },
        }


generation_job_orchestrator_service = GenerationJobOrchestratorService()
