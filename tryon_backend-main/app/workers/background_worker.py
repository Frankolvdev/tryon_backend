import logging
import multiprocessing
import os
import signal
import socket
import time
from typing import Any

from app.common.job_enums import (
    JobExecutionMode,
    JobStatus,
)
from app.db.database import SessionLocal
from app.repositories.background_job_repository import (
    background_job_repository,
)
from app.schemas.background_job_runtime import (
    BackgroundJobClaimRequest,
    BackgroundJobHeartbeatRequest,
)
from app.services.background_job_claim_service import (
    background_job_claim_service,
)
from app.services.background_job_completion_service import (
    background_job_completion_service,
)
from app.services.background_job_redis_service import (
    background_job_redis_service,
)
from app.services.comfyui_local_adapter_service import (
    comfyui_local_adapter_service,
)
from app.services.runpod_serverless_adapter_service import (
    runpod_serverless_adapter_service,
)
from app.workers.handler_registry import (
    internal_job_handler_registry,
)
from app.workers.job_child_process import (
    execute_comfyui_job_child,
    execute_internal_job_child,
    execute_runpod_job_child,
)


logger = logging.getLogger(__name__)


class BackgroundWorker:
    def __init__(
        self,
        *,
        queue_name: str,
        worker_name: str | None = None,
        worker_version: str = "1.0.0",
        lease_seconds: int = 120,
        heartbeat_seconds: int = 15,
        redis_wait_seconds: int = 5,
        poll_seconds: float = 2.0,
    ):
        self.queue_name = queue_name

        self.worker_name = (
            worker_name
            or self._default_worker_name()
        )

        self.worker_version = worker_version
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = (
            heartbeat_seconds
        )
        self.redis_wait_seconds = (
            redis_wait_seconds
        )
        self.poll_seconds = poll_seconds

        self._stop_requested = False
        self._current_process = None
        self._current_prompt_id = None
        self._current_runpod_job_id = None
        self._current_runpod_endpoint_id = None

    def _default_worker_name(self) -> str:
        return (
            f"{socket.gethostname()}-"
            f"{os.getpid()}"
        )

    def request_stop(
        self,
        *_args,
    ) -> None:
        self._stop_requested = True

        logger.info(
            "Worker shutdown requested: %s",
            self.worker_name,
        )

        if self._current_prompt_id:
            (
                comfyui_local_adapter_service
                .cancel_prompt(
                    prompt_id=(
                        self._current_prompt_id
                    )
                )
            )

        if (
            self._current_runpod_job_id
            and self._current_runpod_endpoint_id
        ):
            db = SessionLocal()

            try:
                (
                    runpod_serverless_adapter_service
                    .cancel_job(
                        db,
                        provider_job_id=(
                            self
                            ._current_runpod_job_id
                        ),
                        endpoint_id=(
                            self
                            ._current_runpod_endpoint_id
                        ),
                    )
                )
            except Exception:
                logger.exception(
                    "Could not cancel current "
                    "RunPod job during shutdown."
                )
            finally:
                db.close()

    def install_signal_handlers(self) -> None:
        signal.signal(
            signal.SIGINT,
            self.request_stop,
        )

        if hasattr(signal, "SIGTERM"):
            signal.signal(
                signal.SIGTERM,
                self.request_stop,
            )

    def _claim_one(self):
        db = SessionLocal()

        try:
            response = (
                background_job_claim_service.claim(
                    db,
                    data=BackgroundJobClaimRequest(
                        worker_name=self.worker_name,
                        worker_version=(
                            self.worker_version
                        ),
                        queue_name=self.queue_name,
                        max_jobs=1,
                        lease_seconds=(
                            self.lease_seconds
                        ),
                    ),
                )
            )

            return (
                response.items[0]
                if response.items
                else None
            )

        finally:
            db.close()

    def _start_job(
        self,
        *,
        job_id: int,
        lease_token: str,
    ):
        db = SessionLocal()

        try:
            return background_job_claim_service.start(
                db,
                job_id=job_id,
                worker_name=self.worker_name,
                lease_token=lease_token,
            )
        finally:
            db.close()

    def _heartbeat(
        self,
        *,
        job_id: int,
        lease_token: str,
        progress: float | None = None,
        message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        db = SessionLocal()

        try:
            return (
                background_job_claim_service
                .heartbeat(
                    db,
                    job_id=job_id,
                    data=(
                        BackgroundJobHeartbeatRequest(
                            worker_name=(
                                self.worker_name
                            ),
                            lease_token=lease_token,
                            lease_seconds=(
                                self.lease_seconds
                            ),
                            progress=progress,
                            progress_message=message,
                            metadata=(
                                metadata or {}
                            ),
                        )
                    ),
                )
            )
        finally:
            db.close()

    def _complete_success(
        self,
        *,
        job_id: int,
        lease_token: str,
        result: dict[str, Any],
        metrics: dict[str, Any],
    ):
        db = SessionLocal()

        try:
            return (
                background_job_completion_service
                .succeed(
                    db,
                    job_id=job_id,
                    worker_name=self.worker_name,
                    lease_token=lease_token,
                    result=result,
                    metrics=metrics,
                )
            )
        finally:
            db.close()

    def _complete_failure(
        self,
        *,
        job_id: int,
        lease_token: str,
        error_code: str,
        error_message: str,
        error_details: dict[str, Any],
        metrics: dict[str, Any],
        timed_out: bool = False,
        retryable: bool = True,
    ):
        db = SessionLocal()

        try:
            return (
                background_job_completion_service
                .fail(
                    db,
                    job_id=job_id,
                    worker_name=self.worker_name,
                    lease_token=lease_token,
                    error_code=error_code,
                    error_message=error_message,
                    error_details=error_details,
                    metrics=metrics,
                    timed_out=timed_out,
                    retryable=retryable,
                )
            )
        finally:
            db.close()

    def _complete_cancellation(
        self,
        *,
        job_id: int,
        lease_token: str,
        reason: str,
    ):
        db = SessionLocal()

        try:
            return (
                background_job_completion_service
                .cancel(
                    db,
                    job_id=job_id,
                    worker_name=self.worker_name,
                    lease_token=lease_token,
                    reason=reason,
                )
            )
        finally:
            db.close()

    def _read_job_state(
        self,
        *,
        job_id: int,
    ) -> tuple[str | None, int | None]:
        db = SessionLocal()

        try:
            job = (
                background_job_repository
                .get_by_id(
                    db,
                    job_id,
                )
            )

            if not job:
                return None, None

            return (
                job.status,
                job.timeout_seconds,
            )
        finally:
            db.close()

    def _set_provider_job_id(
        self,
        *,
        job_id: int,
        provider_job_id: str,
        provider_endpoint_id: str | None,
    ) -> None:
        db = SessionLocal()

        try:
            job = (
                background_job_repository
                .get_for_update(
                    db,
                    job_id,
                )
            )

            if not job:
                db.rollback()
                return

            job.provider_job_id = (
                provider_job_id
            )

            job.provider_endpoint_id = (
                provider_endpoint_id
            )

            db.add(job)
            db.commit()
        finally:
            db.close()

    def _terminate_child(
        self,
        process: multiprocessing.Process,
    ) -> None:
        if not process.is_alive():
            return

        process.terminate()
        process.join(timeout=5)

        if (
            process.is_alive()
            and hasattr(process, "kill")
        ):
            process.kill()
            process.join(timeout=5)

    def _cancel_provider_job(
        self,
        *,
        execution_mode: str,
        prompt_id: str | None,
        provider_job_id: str | None,
        endpoint_id: str | None,
    ) -> None:
        if (
            execution_mode
            == JobExecutionMode
            .COMFYUI_LOCAL
            .value
            and prompt_id
        ):
            (
                comfyui_local_adapter_service
                .cancel_prompt(
                    prompt_id=prompt_id
                )
            )

        if (
            execution_mode
            == JobExecutionMode
            .RUNPOD_SERVERLESS
            .value
            and provider_job_id
            and endpoint_id
        ):
            db = SessionLocal()

            try:
                (
                    runpod_serverless_adapter_service
                    .cancel_job(
                        db,
                        provider_job_id=(
                            provider_job_id
                        ),
                        endpoint_id=endpoint_id,
                    )
                )
            finally:
                db.close()

    def _monitor_child_process(
        self,
        *,
        process: multiprocessing.Process,
        result_queue,
        job_id: int,
        lease_token: str,
        timeout_seconds: int,
        execution_mode: str,
        prompt_id: str | None = None,
        provider_job_id: str | None = None,
        endpoint_id: str | None = None,
    ) -> None:
        started_at = time.monotonic()
        last_heartbeat_at = 0.0

        try:
            while process.is_alive():
                elapsed = (
                    time.monotonic()
                    - started_at
                )

                status, _ = (
                    self._read_job_state(
                        job_id=job_id
                    )
                )

                if (
                    status
                    == JobStatus
                    .CANCEL_REQUESTED
                    .value
                    or self._stop_requested
                ):
                    self._cancel_provider_job(
                        execution_mode=(
                            execution_mode
                        ),
                        prompt_id=prompt_id,
                        provider_job_id=(
                            provider_job_id
                        ),
                        endpoint_id=endpoint_id,
                    )

                    self._terminate_child(
                        process
                    )

                    self._complete_cancellation(
                        job_id=job_id,
                        lease_token=lease_token,
                        reason=(
                            "Job execution was "
                            "canceled."
                        ),
                    )

                    return

                if elapsed >= timeout_seconds:
                    self._cancel_provider_job(
                        execution_mode=(
                            execution_mode
                        ),
                        prompt_id=prompt_id,
                        provider_job_id=(
                            provider_job_id
                        ),
                        endpoint_id=endpoint_id,
                    )

                    self._terminate_child(
                        process
                    )

                    self._complete_failure(
                        job_id=job_id,
                        lease_token=lease_token,
                        error_code="job_timeout",
                        error_message=(
                            "Job exceeded its "
                            "configured timeout of "
                            f"{timeout_seconds} seconds."
                        ),
                        error_details={
                            "timeout_seconds": (
                                timeout_seconds
                            ),
                            "elapsed_seconds": (
                                elapsed
                            ),
                            "execution_mode": (
                                execution_mode
                            ),
                            "prompt_id": prompt_id,
                            "provider_job_id": (
                                provider_job_id
                            ),
                            "endpoint_id": (
                                endpoint_id
                            ),
                        },
                        metrics={
                            "duration_seconds": (
                                elapsed
                            ),
                        },
                        timed_out=True,
                        retryable=True,
                    )

                    return

                if (
                    elapsed - last_heartbeat_at
                    >= self.heartbeat_seconds
                ):
                    self._heartbeat(
                        job_id=job_id,
                        lease_token=lease_token,
                        message=(
                            "Job execution is running."
                        ),
                        metadata={
                            "execution_mode": (
                                execution_mode
                            ),
                            "prompt_id": prompt_id,
                            "provider_job_id": (
                                provider_job_id
                            ),
                            "endpoint_id": endpoint_id,
                            "elapsed_seconds": (
                                elapsed
                            ),
                        },
                    )

                    last_heartbeat_at = elapsed

                process.join(timeout=1)

            process.join(timeout=2)

            if result_queue.empty():
                self._complete_failure(
                    job_id=job_id,
                    lease_token=lease_token,
                    error_code=(
                        "worker_child_no_result"
                    ),
                    error_message=(
                        "The child process finished "
                        "without returning a result."
                    ),
                    error_details={
                        "exit_code": (
                            process.exitcode
                        ),
                        "execution_mode": (
                            execution_mode
                        ),
                        "prompt_id": prompt_id,
                        "provider_job_id": (
                            provider_job_id
                        ),
                    },
                    metrics={
                        "duration_seconds": (
                            time.monotonic()
                            - started_at
                        ),
                    },
                    retryable=True,
                )

                return

            child_result = result_queue.get()

            if child_result.get("success"):
                self._complete_success(
                    job_id=job_id,
                    lease_token=lease_token,
                    result=child_result.get(
                        "result",
                        {},
                    ),
                    metrics=child_result.get(
                        "metrics",
                        {},
                    ),
                )

                return

            error_code = child_result.get(
                "error_code",
                "job_execution_failed",
            )

            self._complete_failure(
                job_id=job_id,
                lease_token=lease_token,
                error_code=error_code,
                error_message=child_result.get(
                    "error_message",
                    "Job execution failed.",
                ),
                error_details=child_result.get(
                    "error_details",
                    {},
                ),
                metrics=child_result.get(
                    "metrics",
                    {},
                ),
                timed_out=(
                    error_code == "TimeoutError"
                ),
                retryable=True,
            )

        finally:
            if process.is_alive():
                self._terminate_child(process)

            result_queue.close()

            self._current_process = None
            self._current_prompt_id = None
            self._current_runpod_job_id = None
            self._current_runpod_endpoint_id = None

    def _execute_internal_job(
        self,
        *,
        job_id: int,
        job_type: str,
        payload: dict[str, Any],
        lease_token: str,
        timeout_seconds: int,
    ) -> None:
        if not (
            internal_job_handler_registry
            .exists(job_type)
        ):
            self._complete_failure(
                job_id=job_id,
                lease_token=lease_token,
                error_code=(
                    "handler_not_registered"
                ),
                error_message=(
                    "No internal handler is "
                    "registered for job type "
                    f"'{job_type}'."
                ),
                error_details={
                    "job_type": job_type,
                },
                metrics={},
                retryable=False,
            )

            return

        context = multiprocessing.get_context(
            "spawn"
        )

        result_queue = context.Queue()

        process = context.Process(
            target=execute_internal_job_child,
            kwargs={
                "result_queue": result_queue,
                "job_type": job_type,
                "payload": payload,
            },
            daemon=False,
        )

        self._current_process = process
        process.start()

        self._monitor_child_process(
            process=process,
            result_queue=result_queue,
            job_id=job_id,
            lease_token=lease_token,
            timeout_seconds=timeout_seconds,
            execution_mode=(
                JobExecutionMode
                .INTERNAL
                .value
            ),
        )

    def _extract_workflow(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        workflow = payload.get("workflow")

        if isinstance(workflow, dict):
            return workflow

        prompt = payload.get("prompt")

        if isinstance(prompt, dict):
            return prompt

        raise ValueError(
            "The payload must contain a "
            "ComfyUI workflow object."
        )

    def _execute_comfyui_job(
        self,
        *,
        job_id: int,
        job_public_id: str,
        payload: dict[str, Any],
        lease_token: str,
        timeout_seconds: int,
    ) -> None:
        health = (
            comfyui_local_adapter_service
            .health()
        )

        if not health.get("available"):
            self._complete_failure(
                job_id=job_id,
                lease_token=lease_token,
                error_code=(
                    "comfyui_unavailable"
                ),
                error_message=(
                    "Local ComfyUI is not "
                    "available."
                ),
                error_details=health,
                metrics={},
                retryable=True,
            )

            return

        try:
            queued = (
                comfyui_local_adapter_service
                .queue_prompt(
                    workflow=(
                        self._extract_workflow(
                            payload
                        )
                    ),
                    client_id=payload.get(
                        "client_id"
                    ),
                    extra_data=payload.get(
                        "extra_data"
                    ),
                )
            )
        except Exception as error:
            self._complete_failure(
                job_id=job_id,
                lease_token=lease_token,
                error_code=(
                    error.__class__.__name__
                ),
                error_message=str(error),
                error_details={
                    "provider": (
                        "comfyui_local"
                    ),
                },
                metrics={},
                retryable=True,
            )

            return

        prompt_id = queued["prompt_id"]
        client_id = queued["client_id"]

        self._current_prompt_id = prompt_id

        self._set_provider_job_id(
            job_id=job_id,
            provider_job_id=prompt_id,
            provider_endpoint_id=(
                comfyui_local_adapter_service
                ._base_url()
            ),
        )

        context = multiprocessing.get_context(
            "spawn"
        )

        result_queue = context.Queue()

        process = context.Process(
            target=execute_comfyui_job_child,
            kwargs={
                "result_queue": result_queue,
                "prompt_id": prompt_id,
                "client_id": client_id,
                "job_public_id": (
                    job_public_id
                ),
                "timeout_seconds": (
                    timeout_seconds
                ),
                "download_outputs": bool(
                    payload.get(
                        "download_outputs",
                        True,
                    )
                ),
            },
            daemon=False,
        )

        self._current_process = process
        process.start()

        self._monitor_child_process(
            process=process,
            result_queue=result_queue,
            job_id=job_id,
            lease_token=lease_token,
            timeout_seconds=timeout_seconds,
            execution_mode=(
                JobExecutionMode
                .COMFYUI_LOCAL
                .value
            ),
            prompt_id=prompt_id,
        )

    def _runpod_input(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        input_data = payload.get("input")

        if isinstance(input_data, dict):
            return input_data

        workflow = payload.get("workflow")

        if isinstance(workflow, dict):
            return {
                "workflow": workflow,
                **{
                    key: value
                    for key, value
                    in payload.items()
                    if key not in {
                        "workflow",
                        "endpoint_id",
                        "webhook_url",
                        "policy",
                        "download_outputs",
                    }
                },
            }

        return {
            key: value
            for key, value in payload.items()
            if key not in {
                "endpoint_id",
                "webhook_url",
                "policy",
                "download_outputs",
            }
        }

    def _execute_runpod_job(
        self,
        *,
        job_id: int,
        job_public_id: str,
        payload: dict[str, Any],
        lease_token: str,
        timeout_seconds: int,
    ) -> None:
        db = SessionLocal()

        try:
            submitted = (
                runpod_serverless_adapter_service
                .submit_job(
                    db,
                    input_data=(
                        self._runpod_input(
                            payload
                        )
                    ),
                    endpoint_id=payload.get(
                        "endpoint_id"
                    ),
                    webhook_url=payload.get(
                        "webhook_url"
                    ),
                    policy=payload.get(
                        "policy"
                    ),
                )
            )
        except Exception as error:
            db.rollback()

            self._complete_failure(
                job_id=job_id,
                lease_token=lease_token,
                error_code=(
                    error.__class__.__name__
                ),
                error_message=str(error),
                error_details={
                    "provider": (
                        "runpod_serverless"
                    ),
                },
                metrics={},
                retryable=True,
            )

            return
        finally:
            db.close()

        provider_job_id = (
            submitted["provider_job_id"]
        )

        endpoint_id = (
            submitted["endpoint_id"]
        )

        self._current_runpod_job_id = (
            provider_job_id
        )

        self._current_runpod_endpoint_id = (
            endpoint_id
        )

        self._set_provider_job_id(
            job_id=job_id,
            provider_job_id=(
                provider_job_id
            ),
            provider_endpoint_id=(
                endpoint_id
            ),
        )

        self._heartbeat(
            job_id=job_id,
            lease_token=lease_token,
            progress=2.0,
            message=(
                "Job submitted to RunPod."
            ),
            metadata={
                "provider": (
                    "runpod_serverless"
                ),
                "provider_job_id": (
                    provider_job_id
                ),
                "endpoint_id": endpoint_id,
                "provider_status": (
                    submitted["status"]
                ),
            },
        )

        context = multiprocessing.get_context(
            "spawn"
        )

        result_queue = context.Queue()

        process = context.Process(
            target=execute_runpod_job_child,
            kwargs={
                "result_queue": result_queue,
                "provider_job_id": (
                    provider_job_id
                ),
                "endpoint_id": endpoint_id,
                "job_public_id": (
                    job_public_id
                ),
                "timeout_seconds": (
                    timeout_seconds
                ),
                "download_outputs": bool(
                    payload.get(
                        "download_outputs",
                        True,
                    )
                ),
            },
            daemon=False,
        )

        self._current_process = process
        process.start()

        self._monitor_child_process(
            process=process,
            result_queue=result_queue,
            job_id=job_id,
            lease_token=lease_token,
            timeout_seconds=timeout_seconds,
            execution_mode=(
                JobExecutionMode
                .RUNPOD_SERVERLESS
                .value
            ),
            provider_job_id=(
                provider_job_id
            ),
            endpoint_id=endpoint_id,
        )

    def execute_claimed_item(
        self,
        claimed_item,
    ) -> None:
        job = claimed_item.job
        lease_token = (
            claimed_item.lease_token
        )

        try:
            started_job = self._start_job(
                job_id=job.id,
                lease_token=lease_token,
            )

            if (
                started_job.status
                == JobStatus
                .CANCEL_REQUESTED
            ):
                self._complete_cancellation(
                    job_id=job.id,
                    lease_token=lease_token,
                    reason=(
                        "Job was canceled "
                        "before execution."
                    ),
                )

                return

            if (
                started_job.execution_mode
                == JobExecutionMode.INTERNAL
            ):
                self._execute_internal_job(
                    job_id=started_job.id,
                    job_type=(
                        started_job.job_type
                    ),
                    payload=started_job.payload,
                    lease_token=lease_token,
                    timeout_seconds=(
                        started_job
                        .timeout_seconds
                    ),
                )

                return

            if (
                started_job.execution_mode
                == JobExecutionMode
                .COMFYUI_LOCAL
            ):
                self._execute_comfyui_job(
                    job_id=started_job.id,
                    job_public_id=(
                        started_job.public_id
                    ),
                    payload=started_job.payload,
                    lease_token=lease_token,
                    timeout_seconds=(
                        started_job
                        .timeout_seconds
                    ),
                )

                return

            if (
                started_job.execution_mode
                == JobExecutionMode
                .RUNPOD_SERVERLESS
            ):
                self._execute_runpod_job(
                    job_id=started_job.id,
                    job_public_id=(
                        started_job.public_id
                    ),
                    payload=started_job.payload,
                    lease_token=lease_token,
                    timeout_seconds=(
                        started_job
                        .timeout_seconds
                    ),
                )

                return

            self._complete_failure(
                job_id=job.id,
                lease_token=lease_token,
                error_code=(
                    "unsupported_execution_mode"
                ),
                error_message=(
                    "Unsupported execution mode "
                    f"'{started_job.execution_mode}'."
                ),
                error_details={
                    "execution_mode": (
                        started_job
                        .execution_mode
                        .value
                    ),
                },
                metrics={},
                retryable=False,
            )

        except Exception as error:
            logger.exception(
                "Worker failed while executing "
                "job %s: %s",
                job.id,
                error,
            )

            try:
                self._complete_failure(
                    job_id=job.id,
                    lease_token=lease_token,
                    error_code=(
                        error.__class__.__name__
                    ),
                    error_message=str(error),
                    error_details={},
                    metrics={},
                    retryable=True,
                )
            except Exception:
                logger.exception(
                    "Could not persist failure "
                    "for job %s.",
                    job.id,
                )

    def run_once(self) -> bool:
        claimed_item = self._claim_one()

        if not claimed_item:
            return False

        logger.info(
            "Worker %s claimed job %s (%s).",
            self.worker_name,
            claimed_item.job.public_id,
            claimed_item.job.job_type,
        )

        self.execute_claimed_item(
            claimed_item
        )

        return True

    def run_forever(self) -> None:
        self.install_signal_handlers()

        logger.info(
            "Worker %s started for queue '%s'.",
            self.worker_name,
            self.queue_name,
        )

        while not self._stop_requested:
            executed = self.run_once()

            if executed:
                continue

            signal_payload = (
                background_job_redis_service
                .wait_for_signal(
                    queue_name=self.queue_name,
                    timeout_seconds=(
                        self.redis_wait_seconds
                    ),
                )
            )

            if signal_payload:
                continue

            time.sleep(
                self.poll_seconds
            )

        logger.info(
            "Worker %s stopped.",
            self.worker_name,
        )