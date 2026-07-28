from __future__ import annotations

import os
import signal
import threading
import time
import traceback
from typing import Any

import runpod

from runpod_runtime import (
    RunPodCancellationRequested,
    RunPodGenerationRuntime,
)


os.environ["RUNTIME_PROVIDER"] = "runpod"
runtime = RunPodGenerationRuntime()
_handler_lock = threading.Lock()


def _progress_update(job: dict[str, Any], progress: float, message: str) -> None:
    update = {
        "progress": max(0.0, min(float(progress), 100.0)),
        "message": str(message),
        "provider": "runpod",
        "execution_id": str((job.get("input") or {}).get("execution_id") or ""),
        "updated_at_ms": int(time.time() * 1000),
    }
    progress_update = getattr(runpod.serverless, "progress_update", None)
    if callable(progress_update):
        try:
            progress_update(job, update)
        except Exception:
            # Progress reporting is auxiliary and must never fail the pipeline.
            pass


def _cancel_from_signal(signum: int, _frame: Any) -> None:
    print(f"[runpod] Cancellation signal received: {signum}", flush=True)
    runtime.request_cancel()


for _signal in (signal.SIGTERM, signal.SIGINT):
    try:
        signal.signal(_signal, _cancel_from_signal)
    except (ValueError, OSError):
        pass


def handler(job: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(job, dict):
        raise ValueError("RunPod job must be a JSON object.")
    payload = job.get("input") or {}
    if not isinstance(payload, dict):
        raise ValueError("RunPod job input must be a JSON object.")
    if payload.get("runtime_contract") != runtime.CONTRACT:
        raise ValueError("Unsupported Generation Runtime contract.")

    # A single worker must not execute two mutable ComfyUI pipelines at once.
    # Endpoint scaling provides parallelism by creating additional workers.
    with _handler_lock:
        runtime.reset_job_state()
        execution_id = str(payload.get("execution_id") or "")
        print(
            f"[runpod] Pipeline start execution_id={execution_id}",
            flush=True,
        )
        _progress_update(job, 0, "RunPod worker accepted the pipeline.")
        started = time.monotonic()
        try:
            result = runtime.execute(
                payload,
                progress=lambda value, message: _progress_update(
                    job,
                    value,
                    message,
                ),
            )
            if not isinstance(result, dict):
                raise RuntimeError("Generation Runtime returned an invalid result.")
            if result.get("status") == "failed":
                raise RuntimeError(str(result.get("error") or "Pipeline failed."))
            _progress_update(job, 100, "RunPod pipeline completed.")
            print(
                "[runpod] Pipeline end "
                f"execution_id={execution_id} "
                f"duration_ms={int((time.monotonic() - started) * 1000)}",
                flush=True,
            )
            return result
        except RunPodCancellationRequested:
            runtime.cancel_active_prompt()
            print(
                f"[runpod] Pipeline cancelled execution_id={execution_id}",
                flush=True,
            )
            raise
        except BaseException as exc:
            runtime.cancel_active_prompt()
            print(
                "[runpod] Pipeline error "
                f"execution_id={execution_id} "
                f"error_type={exc.__class__.__name__} error={exc}",
                flush=True,
            )
            traceback.print_exc()
            raise
        finally:
            runtime.reset_job_state()


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
