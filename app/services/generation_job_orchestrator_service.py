from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from uuid import UUID

from app.common.generation_module_enums import GenerationExecutionEngine
from app.common.time import utc_now
from app.core.config import settings
from app.db.database import SessionLocal
from app.schemas.generation_module_runtime import GenerationModuleExecutionLog
from app.services.generation_job_queue_service import generation_job_queue_service
from app.services.generation_execution_state_contract import generation_execution_state_contract
from app.services.ai_engine_settings_service import ai_engine_settings_service
from app.services.generation_module_execution_store_service import generation_module_execution_store_service
from app.services.generation_module_service import generation_module_service

logger = logging.getLogger(__name__)


class GenerationJobOrchestratorService:
    """Durable provider orchestration without coupling remote capacity to local threads.

    Redis owns waiting jobs. PostgreSQL owns durable execution state. Remote providers
    own GPU execution. Modal is special because a durable FunctionCall ID allows the
    backend to submit work and wait asynchronously without holding one Redis BLPOP,
    one SQL connection, or one Python worker thread for the lifetime of every GPU job.
    """

    def __init__(self) -> None:
        self._runtime = None
        self._threads: list[threading.Thread] = []
        self._stop = threading.Event()
        self._started = False
        self._lock = threading.Lock()
        self._runtime_settings = None

        # Modal capacity is remote execution capacity, not a worker/thread count.
        self._modal_capacity = 0
        self._modal_queue_dispatchers = 0
        self._modal_reserved = 0
        self._modal_active_ids: set[UUID] = set()
        self._modal_capacity_condition = threading.Condition(threading.RLock())

        # One asyncio loop supervises many Modal FunctionCalls without one thread/job.
        self._modal_loop: asyncio.AbstractEventLoop | None = None
        self._modal_loop_thread: threading.Thread | None = None
        self._modal_watch_futures: dict[UUID, Future] = {}
        self._modal_watch_lock = threading.RLock()
        self._modal_finalizer_executor: ThreadPoolExecutor | None = None

    def bind(self, runtime) -> None:
        self._runtime = runtime

    def _start_modal_supervisor_loop(self) -> None:
        if self._modal_loop_thread and self._modal_loop_thread.is_alive():
            return

        ready = threading.Event()

        def runner() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            finalizer_workers = max(
                1,
                int(getattr(settings, "GENERATION_MODAL_FINALIZER_WORKERS", 16)),
            )
            executor = ThreadPoolExecutor(
                max_workers=finalizer_workers,
                thread_name_prefix="generation-modal-finalizer",
            )
            loop.set_default_executor(executor)
            self._modal_loop = loop
            self._modal_finalizer_executor = executor
            ready.set()
            try:
                loop.run_forever()
            finally:
                # Remote Modal calls are durable. Local wait tasks may disappear on
                # process shutdown and are restored from provider_job_id on startup.
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.close()

        self._modal_loop_thread = threading.Thread(
            target=runner,
            name="generation-modal-supervisor-loop",
            daemon=True,
        )
        self._modal_loop_thread.start()
        if not ready.wait(timeout=10):
            raise RuntimeError("Modal async supervisor loop could not start.")

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            if self._runtime is None:
                raise RuntimeError("Generation runtime is not bound to the orchestrator.")
            self._started = True
            self._stop.clear()
            db = SessionLocal()
            try:
                self._runtime_settings = ai_engine_settings_service.get(db)
            finally:
                db.close()

            self._modal_capacity = max(
                1,
                int(self._runtime_settings.modal_max_containers)
                * int(self._runtime_settings.modal_concurrency),
            )
            configured_dispatchers = max(
                1,
                int(getattr(settings, "GENERATION_MODAL_QUEUE_DISPATCHERS", 16)),
            )
            # More dispatchers than remote slots never help, but remote capacity may
            # be thousands without creating thousands of local Redis consumers.
            self._modal_queue_dispatchers = min(
                self._modal_capacity,
                configured_dispatchers,
            )

        self._start_modal_supervisor_loop()

        # Recovery MUST happen before queue consumers start. This registers already
        # running Modal FunctionCalls against remote capacity first, preventing a
        # restart stampede from over-dispatching queued work.
        self.recover_pending()

        with self._lock:
            runpod_parallelism = min(
                self._runtime_settings.runpod_dispatch_workers,
                self._runtime_settings.runpod_max_in_flight,
            )
            specs = [
                ("local", self._runtime_settings.local_parallel_executions),
                ("runpod", runpod_parallelism),
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

            for index in range(self._modal_queue_dispatchers):
                thread = threading.Thread(
                    target=self._modal_dispatch_loop,
                    name=f"generation-modal-dispatcher-{index + 1}",
                    daemon=True,
                )
                thread.start()
                self._threads.append(thread)

            reconcile_thread = threading.Thread(
                target=self._modal_reconcile_loop,
                name="generation-modal-reconciler",
                daemon=True,
            )
            reconcile_thread.start()
            self._threads.append(reconcile_thread)

        logger.info(
            "Generation orchestrator started: modal_capacity=%s modal_queue_dispatchers=%s "
            "modal_finalizers=%s runpod=%s local=%s beam=%s simulated=%s",
            self._modal_capacity,
            self._modal_queue_dispatchers,
            max(1, int(getattr(settings, "GENERATION_MODAL_FINALIZER_WORKERS", 16))),
            runpod_parallelism,
            self._runtime_settings.local_parallel_executions,
            5,
            max(1, int(settings.GENERATION_SIMULATED_WORKERS)),
        )

    def stop(self) -> None:
        self._stop.set()
        with self._modal_capacity_condition:
            self._modal_capacity_condition.notify_all()

        for thread in self._threads:
            thread.join(timeout=3)
        self._threads.clear()

        with self._modal_watch_lock:
            futures = list(self._modal_watch_futures.values())
            self._modal_watch_futures.clear()
        for future in futures:
            future.cancel()

        loop = self._modal_loop
        if loop and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        if self._modal_loop_thread:
            self._modal_loop_thread.join(timeout=5)
        if self._modal_finalizer_executor:
            self._modal_finalizer_executor.shutdown(wait=False, cancel_futures=True)

        self._modal_loop = None
        self._modal_loop_thread = None
        self._modal_finalizer_executor = None
        with self._modal_capacity_condition:
            self._modal_reserved = 0
            self._modal_active_ids.clear()
        self._started = False

    def submit(self, execution_id: UUID, *, engine: GenerationExecutionEngine) -> str:
        self.start()
        return generation_job_queue_service.enqueue(execution_id, engine=engine)

    @staticmethod
    def _iter_persisted(*, status: str, engine: str | None = None, page_size: int = 500):
        """Page durable history so recovery is not capped at 10,000 executions."""
        skip = 0
        while True:
            items, total = generation_module_execution_store_service.list(
                status=status,
                engine=engine,
                skip=skip,
                limit=page_size,
            )
            if not items:
                break
            for item in items:
                yield item
            skip += len(items)
            if skip >= total:
                break

    def recover_pending(self) -> None:
        # Queued work remains Redis-owned. SADD dedupe keeps repeated startup
        # recovery idempotent if the queue already contains the execution.
        for item in self._iter_persisted(status="queued"):
            if generation_execution_state_contract.is_dispatchable(item):
                generation_job_queue_service.enqueue(item.id, engine=item.engine)

        # Snapshot running rows before mutating any state. This avoids pagination
        # skips if already-completed Modal calls finalize immediately during startup.
        running_items = list(self._iter_persisted(status="running"))

        recovery_batch_size = max(
            1,
            int(getattr(settings, "GENERATION_MODAL_RECOVERY_BATCH_SIZE", 50)),
        )
        recovery_batch_delay = max(
            0.0,
            float(getattr(settings, "GENERATION_MODAL_RECOVERY_BATCH_DELAY_MS", 250)) / 1000.0,
        )
        recovered_modal = 0

        # Running Modal work is NOT requeued. Its durable FunctionCall ID is the
        # identity of the already-running provider job and must be supervised.
        for item in running_items:
            if item.engine == GenerationExecutionEngine.MODAL and item.provider_job_id:
                self._runtime.attach_persisted(item)
                with self._runtime._lock:
                    tracked = self._runtime._items[item.id]
                    tracked.recovery_count += 1
                    tracked.recovered_at = utc_now()
                    tracked.logs.append(self._runtime.recovery_log())
                    snapshot = tracked.model_copy(deep=True)
                generation_module_execution_store_service.save(snapshot)
                self._register_modal_active(item.id)
                self._schedule_modal_supervision(item.id)
                recovered_modal += 1
                # Controlled restart ramp: avoid reconnecting thousands of durable
                # FunctionCalls to the Modal control plane in one instant. This
                # throttle exists only during recovery; normal result delivery uses
                # event-driven get.aio() and has no polling delay.
                if (
                    recovery_batch_delay > 0
                    and recovered_modal % recovery_batch_size == 0
                    and not self._stop.is_set()
                ):
                    self._stop.wait(recovery_batch_delay)
                continue

            # Preserve the established fail-closed behavior for providers that do
            # not have a durable resumable provider ID in this orchestrator.
            item.status = "failed"
            item.error = "Execution could not be resumed safely after backend restart; no retry was created."
            item.finished_at = utc_now()
            item.provider_status = "RECOVERY_FAILED"
            item.logs.append(
                GenerationModuleExecutionLog(
                    timestamp=item.finished_at,
                    level="error",
                    message=item.error,
                )
            )
            generation_module_execution_store_service.save(item)

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
        """Existing worker model for Local, RunPod, Beam and simulation."""
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
                if current is None or current.status not in {"queued", "running"} or current.cancel_requested:
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

    def _acquire_modal_reservation(self) -> bool:
        with self._modal_capacity_condition:
            while not self._stop.is_set():
                used = len(self._modal_active_ids) + self._modal_reserved
                if used < self._modal_capacity:
                    self._modal_reserved += 1
                    return True
                self._modal_capacity_condition.wait(timeout=0.5)
            return False

    def _release_modal_reservation(self) -> None:
        with self._modal_capacity_condition:
            self._modal_reserved = max(0, self._modal_reserved - 1)
            self._modal_capacity_condition.notify_all()

    def _promote_modal_reservation(self, execution_id: UUID) -> None:
        with self._modal_capacity_condition:
            self._modal_reserved = max(0, self._modal_reserved - 1)
            self._modal_active_ids.add(execution_id)
            self._modal_capacity_condition.notify_all()

    def _register_modal_active(self, execution_id: UUID) -> None:
        with self._modal_capacity_condition:
            self._modal_active_ids.add(execution_id)
            self._modal_capacity_condition.notify_all()

    def _release_modal_active(self, execution_id: UUID) -> None:
        with self._modal_capacity_condition:
            self._modal_active_ids.discard(execution_id)
            self._modal_capacity_condition.notify_all()

    def _modal_dispatch_loop(self) -> None:
        """Dispatch Modal jobs only while remote execution capacity has free slots.

        A slot is reserved before BLPOP, so overflow jobs remain durably in Redis
        instead of being pulled into an unbounded process-local waiting list.
        """
        while not self._stop.is_set():
            if not self._acquire_modal_reservation():
                return

            raw_id: str | None = None
            execution_id: UUID | None = None
            try:
                raw_id = generation_job_queue_service.dequeue(
                    "modal",
                    timeout_seconds=int(
                        self._runtime_settings.queue_block_seconds
                        if self._runtime_settings
                        else settings.GENERATION_QUEUE_BLOCK_SECONDS
                    ),
                )
                if not raw_id:
                    self._release_modal_reservation()
                    continue

                execution_id = UUID(raw_id)
                current = generation_module_execution_store_service.get(execution_id)
                if (
                    current is None
                    or current.status != "queued"
                    or current.cancel_requested
                ):
                    self._release_modal_reservation()
                    continue

                db = SessionLocal()
                try:
                    module = generation_module_service.get_response(
                        db,
                        module_id=current.module_id,
                    )
                    module_payload = module.model_dump(mode="python")
                finally:
                    db.close()

                self._runtime.attach_persisted(current)
                call_id = self._runtime.dispatch_modal_supervised(
                    execution_id,
                    module_payload,
                )
                if not call_id:
                    raise RuntimeError("Modal dispatch did not persist a FunctionCall ID.")

                self._promote_modal_reservation(execution_id)
                if not self._schedule_modal_supervision(execution_id):
                    # The FunctionCall is already durable and persisted. Keep its
                    # capacity occupied; the reconciler will attach supervision.
                    logger.error(
                        "Modal FunctionCall was submitted but its async supervisor could not be scheduled yet: execution_id=%s call_id=%s",
                        execution_id,
                        call_id,
                    )
            except BaseException as exc:
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                if execution_id is None:
                    self._release_modal_reservation()
                    logger.exception("Modal queue dispatcher failed before execution resolution: %s", raw_id)
                    continue

                # If submit succeeded, provider_job_id is already persisted and the
                # reconciler must supervise that durable call rather than fail it.
                persisted = generation_module_execution_store_service.get(execution_id)
                if persisted and persisted.provider_job_id and persisted.status == "running":
                    self._promote_modal_reservation(execution_id)
                    self._runtime.attach_persisted(persisted)
                    self._schedule_modal_supervision(execution_id)
                    logger.exception(
                        "Modal dispatcher raised after durable submission; supervision retained execution_id=%s call_id=%s",
                        execution_id,
                        persisted.provider_job_id,
                    )
                    continue

                self._release_modal_reservation()
                logger.exception("Modal dispatch failed for %s", execution_id)
                try:
                    self._runtime.finalize_modal_supervised(
                        execution_id,
                        error=exc,
                    )
                except Exception:
                    logger.exception("Could not finalize Modal dispatch failure for %s", execution_id)

    def _schedule_modal_supervision(self, execution_id: UUID) -> bool:
        loop = self._modal_loop
        if loop is None or not loop.is_running() or self._stop.is_set():
            return False
        with self._modal_watch_lock:
            existing = self._modal_watch_futures.get(execution_id)
            if existing is not None and not existing.done():
                return True
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._supervise_modal_execution(execution_id),
                    loop,
                )
            except Exception:
                logger.exception("Could not submit Modal supervisor coroutine for %s", execution_id)
                return False
            self._modal_watch_futures[execution_id] = future

            def cleanup(_future: Future, *, eid: UUID = execution_id) -> None:
                with self._modal_watch_lock:
                    if self._modal_watch_futures.get(eid) is _future:
                        self._modal_watch_futures.pop(eid, None)

            future.add_done_callback(cleanup)
            return True

    async def _supervise_modal_execution(self, execution_id: UUID) -> None:
        """Wait immediately on one durable Modal result without blocking a thread."""
        remote_slot_released = False
        try:
            result = await self._runtime.await_modal_result_async(execution_id)
            # Result availability means Modal execution capacity is free now. Do not
            # hold the remote slot while local storage/billing finalization queues.
            self._release_modal_active(execution_id)
            remote_slot_released = True
            await self._finalize_modal_with_retry(execution_id, result=result)
        except asyncio.CancelledError:
            # Backend shutdown: leave DB state running/provider_job_id intact. Startup
            # recovery recreates this wait without creating a second provider job.
            raise
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            self._release_modal_active(execution_id)
            remote_slot_released = True
            await self._finalize_modal_with_retry(execution_id, error=exc)
        finally:
            if not remote_slot_released and not self._stop.is_set():
                # Defensive only. Normal result/error paths release above.
                self._release_modal_active(execution_id)

    async def _finalize_modal_with_retry(
        self,
        execution_id: UUID,
        *,
        result: dict | None = None,
        error: BaseException | None = None,
    ) -> None:
        max_attempts = max(
            1,
            int(getattr(settings, "GENERATION_MODAL_FINALIZATION_RETRIES", 5)),
        )
        for attempt in range(1, max_attempts + 1):
            if self._stop.is_set():
                return
            try:
                await asyncio.to_thread(
                    self._runtime.finalize_modal_supervised,
                    execution_id,
                    result=result,
                    error=error,
                )
                return
            except Exception as exc:
                logger.exception(
                    "Modal local finalization failed: execution_id=%s attempt=%s/%s",
                    execution_id,
                    attempt,
                    max_attempts,
                )
                if attempt >= max_attempts:
                    # Do not create a new provider call. The periodic reconciler sees
                    # the still-running durable DB row and can retrieve the same
                    # completed FunctionCall again idempotently.
                    return
                await asyncio.sleep(min(10.0, float(attempt)))

    def _modal_reconcile_loop(self) -> None:
        """Low-frequency safety net; never controls normal result latency."""
        interval = max(
            10,
            int(getattr(settings, "GENERATION_MODAL_RECONCILE_SECONDS", 30)),
        )
        while not self._stop.wait(interval):
            try:
                for item in self._iter_persisted(
                    status="running",
                    engine=GenerationExecutionEngine.MODAL.value,
                ):
                    if not item.provider_job_id:
                        continue
                    with self._modal_watch_lock:
                        future = self._modal_watch_futures.get(item.id)
                        watched = future is not None and not future.done()
                    if watched:
                        continue
                    self._runtime.attach_persisted(item)
                    self._register_modal_active(item.id)
                    self._schedule_modal_supervision(item.id)
            except Exception:
                logger.exception("Modal supervision reconciliation failed; next pass will retry.")

    def status(self) -> dict:
        with self._modal_capacity_condition:
            modal_active = len(self._modal_active_ids)
            modal_reserved = self._modal_reserved
        with self._modal_watch_lock:
            modal_supervised = sum(
                1 for future in self._modal_watch_futures.values() if not future.done()
            )
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
                # Keep the existing key and meaning visible to BackOffice: this is
                # Modal execution capacity, not the number of Redis consumers.
                "modal_dispatch": (
                    self._modal_capacity
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
            "modal_supervisor": {
                "capacity": self._modal_capacity,
                "active_remote_calls": modal_active,
                "reserved_dispatch_slots": modal_reserved,
                "queue_dispatchers": self._modal_queue_dispatchers,
                "supervised_calls": modal_supervised,
                "finalizer_workers": max(
                    1,
                    int(getattr(settings, "GENERATION_MODAL_FINALIZER_WORKERS", 16)),
                ),
            },
        }


generation_job_orchestrator_service = GenerationJobOrchestratorService()
