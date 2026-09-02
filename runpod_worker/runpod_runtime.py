from __future__ import annotations

import copy
import json
import threading
import time
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import httpx

from generation_runtime import GenerationRuntime
from generation_runtime.context import GenerationRuntimeContext
from generation_runtime.metrics import RuntimeMetricsCollector


class RunPodCancellationRequested(InterruptedError):
    """Raised when RunPod stops the active serverless job."""


class RunPodGenerationRuntime(GenerationRuntime):
    """RunPod-only lifecycle wrapper around the canonical pipeline runtime.

    Modal continues importing and executing ``GenerationRuntime`` directly.
    This subclass adds RunPod progress, cooperative cancellation checkpoints,
    and ComfyUI prompt cleanup without changing Modal's code path.
    """

    def __init__(self, *, comfy_url: str | None = None) -> None:
        super().__init__(comfy_url=comfy_url)
        self._cancel_event = threading.Event()
        self._active_prompt_id: str | None = None
        self._state_lock = threading.RLock()

    def reset_job_state(self) -> None:
        with self._state_lock:
            self._cancel_event.clear()
            self._active_prompt_id = None

    def request_cancel(self) -> None:
        self._cancel_event.set()
        self.cancel_active_prompt()

    def _raise_if_cancelled(self) -> None:
        if self._cancel_event.is_set():
            raise RunPodCancellationRequested("RunPod job cancellation was requested.")

    def cancel_active_prompt(self) -> None:
        with self._state_lock:
            prompt_id = self._active_prompt_id

        # /interrupt stops the currently executing prompt. Queue deletion is
        # best-effort because the prompt may still be waiting rather than active.
        try:
            with httpx.Client(timeout=10) as client:
                client.post(f"{self.comfy_url}/interrupt", json={})
                if prompt_id:
                    client.post(
                        f"{self.comfy_url}/queue",
                        json={"delete": [prompt_id]},
                    )
        except Exception:
            # RunPod will still terminate/cancel the provider job. Cleanup must
            # never mask the original cancellation signal.
            pass

    def execute(
        self,
        payload: dict[str, Any],
        progress: Callable[[float, str], None] | None = None,
    ) -> dict[str, Any]:
        self.reset_job_state()
        self._raise_if_cancelled()

        if payload.get("runtime_contract") != self.CONTRACT:
            raise ValueError("Unsupported Generation Runtime contract.")

        module = payload.get("module")
        context = self._materialize(
            copy.deepcopy(payload.get("context") or {}),
            self.root / str(payload.get("execution_id") or uuid4()),
        )
        if not isinstance(module, dict):
            raise ValueError("Generation module payload is missing.")

        steps = [
            step
            for step in sorted(
                module.get("steps") or [],
                key=lambda row: row.get("position", 0),
            )
            if step.get("is_enabled")
        ]
        states: list[dict[str, Any]] = []
        metrics = RuntimeMetricsCollector()

        for index, step in enumerate(steps):
            self._raise_if_cancelled()
            started = time.monotonic()
            key = str(step.get("key") or f"step-{index + 1}")
            step_type = str(step.get("step_type") or "")
            try:
                if progress:
                    progress(
                        (index / max(len(steps), 1)) * 100,
                        f"Step '{key}' started.",
                    )

                if step_type == "workflow":
                    outputs = self._workflow(
                        step,
                        context,
                        payload.get("execution_id"),
                    )
                elif step_type == "python":
                    outputs = self._python(
                        step,
                        context,
                        payload.get("execution_id"),
                    )
                elif step_type == "utility":
                    outputs = self._utility(
                        step,
                        context,
                        payload.get("execution_id"),
                    )
                else:
                    raise ValueError(
                        "Unsupported generation module step type: "
                        f"{step_type}"
                    )

                self._raise_if_cancelled()
                GenerationRuntimeContext.merge_step_outputs(
                    context,
                    key,
                    outputs,
                )
                duration_ms = int((time.monotonic() - started) * 1000)
                metrics.add_step(
                    step_key=key,
                    step_type=step_type,
                    duration_ms=duration_ms,
                    status="completed",
                )
                states.append(
                    {
                        "step_key": key,
                        "step_type": step_type,
                        "status": "completed",
                        "duration_ms": duration_ms,
                        "outputs": self._externalize(outputs),
                    }
                )
                if progress:
                    progress(
                        ((index + 1) / max(len(steps), 1)) * 100,
                        f"Step '{key}' completed.",
                    )
            except RunPodCancellationRequested:
                duration_ms = int((time.monotonic() - started) * 1000)
                metrics.add_step(
                    step_key=key,
                    step_type=step_type,
                    duration_ms=duration_ms,
                    status="cancelled",
                )
                self.cancel_active_prompt()
                raise
            except Exception as exc:
                duration_ms = int((time.monotonic() - started) * 1000)
                metrics.add_step(
                    step_key=key,
                    step_type=step_type,
                    duration_ms=duration_ms,
                    status="failed",
                )
                states.append(
                    {
                        "step_key": key,
                        "step_type": step_type,
                        "status": "failed",
                        "duration_ms": duration_ms,
                        "outputs": {},
                        "error": str(exc),
                    }
                )
                return {
                    "runtime_contract": self.CONTRACT,
                    "status": "failed",
                    "error": str(exc),
                    "steps": states,
                    "metrics": metrics.snapshot(),
                }

        self._raise_if_cancelled()
        outputs = GenerationRuntimeContext.resolve_module_outputs(
            module.get("outputs") or [],
            context,
        )
        return {
            "runtime_contract": self.CONTRACT,
            "status": "completed",
            "steps": states,
            "outputs": self._externalize(outputs),
            "context": self._externalize(context),
            "metrics": metrics.snapshot(),
        }

    def _execute_comfy(
        self,
        workflow: dict[str, Any],
        timeout: int,
    ) -> dict[str, Any]:
        self._raise_if_cancelled()
        client_id = uuid4().hex
        with httpx.Client(timeout=60) as client:
            response = client.post(
                f"{self.comfy_url}/prompt",
                json={"prompt": workflow, "client_id": client_id},
            )
            if response.is_error:
                try:
                    detail = response.json()
                except ValueError:
                    detail = response.text
                raise ValueError(
                    "ComfyUI rejected the workflow "
                    f"({response.status_code}): {detail}"
                )
            prompt_id = str(response.json()["prompt_id"])

        with self._state_lock:
            self._active_prompt_id = prompt_id

        started = time.monotonic()
        history = None
        try:
            while time.monotonic() - started < timeout:
                self._raise_if_cancelled()
                with httpx.Client(timeout=60) as client:
                    data = client.get(
                        f"{self.comfy_url}/history/{prompt_id}"
                    ).raise_for_status().json()
                history = data.get(prompt_id)
                if history:
                    break
                time.sleep(1)

            self._raise_if_cancelled()
            if not history:
                self.cancel_active_prompt()
                raise TimeoutError(
                    f"ComfyUI workflow exceeded {timeout} seconds."
                )

            status = history.get("status") or {}
            if isinstance(status, dict) and status.get("status_str") == "error":
                raise RuntimeError(
                    "ComfyUI workflow failed: "
                    + json.dumps(status, ensure_ascii=False, default=str)
                )

            files = []
            for node_id, node_output in (history.get("outputs") or {}).items():
                self._raise_if_cancelled()
                for category in ("images", "gifs", "videos", "audio"):
                    for item in node_output.get(category) or []:
                        self._raise_if_cancelled()
                        params = {
                            "filename": item.get("filename"),
                            "subfolder": item.get("subfolder") or "",
                            "type": item.get("type") or "output",
                        }
                        with httpx.Client(timeout=300) as client:
                            content = client.get(
                                f"{self.comfy_url}/view",
                                params=params,
                            ).raise_for_status().content
                        suffix = (
                            Path(str(item.get("filename") or ".bin")).suffix
                            or ".bin"
                        )
                        target = self.root / f"{uuid4().hex}{suffix}"
                        target.write_bytes(content)
                        files.append(
                            {
                                "__generation_file__": True,
                                "local_path": str(target),
                                "filename": item.get("filename") or target.name,
                                "content_type": item.get("content_type"),
                                "size_bytes": len(content),
                                "node_id": str(node_id),
                            }
                        )
            return {"prompt_id": prompt_id, "files": files}
        finally:
            with self._state_lock:
                if self._active_prompt_id == prompt_id:
                    self._active_prompt_id = None
