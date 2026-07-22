from __future__ import annotations

import copy
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from types import MappingProxyType
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.common.exceptions import AppException, NotFoundException
from app.common.generation_module_enums import GenerationExecutionEngine, GenerationModuleStepType
from app.common.time import utc_now
from app.db.database import SessionLocal
from app.schemas.generation_module_runtime import (
    GenerationModuleExecutionCreate,
    GenerationModuleExecutionLog,
    GenerationModuleExecutionResponse,
    GenerationModuleStepExecution,
)
from app.services.comfyui_local_adapter_service import comfyui_local_adapter_service
from app.services.generation_module_service import generation_module_service
from app.services.runpod_serverless_adapter_service import runpod_serverless_adapter_service


class GenerationModuleRuntimeService:
    def __init__(self) -> None:
        self._items: dict[UUID, GenerationModuleExecutionResponse] = {}
        self._provider_refs: dict[UUID, dict[str, str]] = {}
        self._owners: dict[UUID, int | None] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="generation-module")

    def create(self, db: Session, *, module_id: int, data: GenerationModuleExecutionCreate, user_id: int | None = None) -> GenerationModuleExecutionResponse:
        module = generation_module_service.get_response(db, module_id=module_id)
        if not module.is_active:
            raise AppException("The generation module is inactive.")
        self._validate_inputs(module.inputs, data.inputs)
        engine = data.engine or module.default_execution_engine
        now = utc_now()
        execution = GenerationModuleExecutionResponse(
            id=uuid4(), module_id=module.id, module_key=module.key, user_id=user_id, engine=engine,
            status="queued", progress=0, inputs=copy.deepcopy(data.inputs), context=copy.deepcopy(data.inputs),
            outputs={}, steps=[GenerationModuleStepExecution(step_key=s.key, step_name=s.name, step_type=s.step_type, status="pending") for s in sorted(module.steps, key=lambda item: item.position) if s.is_enabled],
            logs=[GenerationModuleExecutionLog(timestamp=now, message="Execution queued.")], created_at=now,
        )
        with self._lock:
            self._items[execution.id] = execution
            self._owners[execution.id] = user_id
        self._executor.submit(self._run, execution.id, module.model_dump(mode="python"))
        return self.get(execution.id)

    @staticmethod
    def _validate_inputs(definitions: list[Any], values: dict[str, Any]) -> None:
        for item in definitions:
            if item.is_required and item.key not in values and item.default_value is None:
                raise AppException(f"Required module input '{item.key}' is missing.")

    def get(self, execution_id: UUID) -> GenerationModuleExecutionResponse:
        with self._lock:
            item = self._items.get(execution_id)
            if not item:
                raise NotFoundException("Generation module execution not found.")
            return item.model_copy(deep=True)


    def get_for_user(self, execution_id: UUID, *, user_id: int) -> GenerationModuleExecutionResponse:
        with self._lock:
            if self._owners.get(execution_id) != user_id:
                raise NotFoundException("Generation module execution not found.")
        return self.get(execution_id)

    def cancel_for_user(self, execution_id: UUID, *, user_id: int) -> GenerationModuleExecutionResponse:
        self.get_for_user(execution_id, user_id=user_id)
        return self.cancel(execution_id)

    def cancel(self, execution_id: UUID) -> GenerationModuleExecutionResponse:
        with self._lock:
            item = self._items.get(execution_id)
            if not item:
                raise NotFoundException("Generation module execution not found.")
            if item.status in {"completed", "failed", "cancelled"}:
                return item.model_copy(deep=True)
            item.cancel_requested = True
            item.logs.append(GenerationModuleExecutionLog(timestamp=utc_now(), level="warning", message="Cancellation requested."))
            provider = copy.deepcopy(self._provider_refs.get(execution_id) or {})
        if provider.get("engine") == GenerationExecutionEngine.LOCAL_DOCKER.value and provider.get("prompt_id"):
            comfyui_local_adapter_service.cancel_prompt(prompt_id=provider["prompt_id"])
        elif provider.get("engine") == GenerationExecutionEngine.RUNPOD_SERVERLESS.value and provider.get("provider_job_id"):
            db = SessionLocal()
            try:
                runpod_serverless_adapter_service.cancel_job(db, provider_job_id=provider["provider_job_id"], endpoint_id=provider.get("endpoint_id"))
            finally:
                db.close()
        return self.get(execution_id)

    def health(self, db: Session) -> dict[str, Any]:
        try:
            runpod_health = runpod_serverless_adapter_service.health(db)
        except Exception as exc:
            runpod_health = {"available": False, "error": str(exc)}
        return {
            "local_docker": comfyui_local_adapter_service.health(),
            "runpod_serverless": runpod_health,
            "simulated": {"available": True, "mode": "deterministic", "supports_cancel": True, "supports_progress": True},
        }

    def _run(self, execution_id: UUID, module: dict[str, Any]) -> None:
        started = utc_now()
        db = SessionLocal()
        with self._lock:
            item = self._items[execution_id]
            item.status = "running"; item.started_at = started
            item.logs.append(GenerationModuleExecutionLog(timestamp=started, message="Execution started."))
        try:
            steps = [s for s in sorted(module["steps"], key=lambda row: row["position"]) if s["is_enabled"]]
            for index, step in enumerate(steps):
                with self._lock:
                    item = self._items[execution_id]
                    if item.cancel_requested:
                        item.status = "cancelled"
                        item.logs.append(GenerationModuleExecutionLog(timestamp=utc_now(), level="warning", message="Execution cancelled."))
                        break
                    state = item.steps[index]
                    state.status = "running"; state.started_at = utc_now()
                    item.logs.append(GenerationModuleExecutionLog(timestamp=state.started_at, step_key=step["key"], message=f"Step '{step['name']}' started."))
                    context = copy.deepcopy(item.context)
                    engine = item.engine
                outputs = self._execute_step(db, execution_id, step, context, engine)
                finished = utc_now()
                with self._lock:
                    item = self._items[execution_id]; state = item.steps[index]
                    state.status = "completed"; state.finished_at = finished
                    state.duration_ms = int((finished - state.started_at).total_seconds() * 1000) if state.started_at else 0
                    state.outputs = outputs
                    item.context[step["key"]] = outputs
                    item.context.update(outputs)
                    item.progress = int(((index + 1) / max(len(steps), 1)) * 90)
                    item.logs.append(GenerationModuleExecutionLog(timestamp=finished, step_key=step["key"], message=f"Step '{step['name']}' completed."))
            with self._lock:
                item = self._items[execution_id]
                if item.status != "cancelled":
                    item.outputs = self._resolve_module_outputs(module["outputs"], item.context)
                    item.status = "completed"; item.progress = 100
                    item.logs.append(GenerationModuleExecutionLog(timestamp=utc_now(), message="Execution completed."))
        except InterruptedError as exc:
            with self._lock:
                item = self._items[execution_id]; item.status = "cancelled"; item.error = str(exc)
                item.logs.append(GenerationModuleExecutionLog(timestamp=utc_now(), level="warning", message=str(exc)))
        except Exception as exc:
            with self._lock:
                item = self._items[execution_id]
                item.status = "failed"; item.error = str(exc)
                running = next((s for s in item.steps if s.status == "running"), None)
                if running:
                    running.status = "failed"; running.error = str(exc); running.finished_at = utc_now()
                item.logs.append(GenerationModuleExecutionLog(timestamp=utc_now(), level="error", step_key=running.step_key if running else None, message=str(exc)))
        finally:
            db.close()
            finished = utc_now()
            with self._lock:
                item = self._items[execution_id]; item.finished_at = finished
                item.duration_ms = int((finished - started).total_seconds() * 1000)
                self._provider_refs.pop(execution_id, None)

    def _execute_step(self, db: Session, execution_id: UUID, step: dict[str, Any], context: dict[str, Any], engine: GenerationExecutionEngine) -> dict[str, Any]:
        if step["step_type"] == GenerationModuleStepType.PYTHON.value:
            return self._execute_python(step, context)
        if step["step_type"] != GenerationModuleStepType.WORKFLOW.value:
            raise AppException(f"Unsupported generation module step type: {step['step_type']}")
        workflow, configuration = self._prepare_workflow(step, context)
        if engine == GenerationExecutionEngine.SIMULATED:
            simulation = configuration.get("simulation") or {}
            duration_ms = max(150, min(int(simulation.get("duration_ms") or 1200), 15000))
            checkpoints = max(2, min(int(simulation.get("checkpoints") or 6), 30))
            for checkpoint in range(1, checkpoints + 1):
                if self.get(execution_id).cancel_requested:
                    raise InterruptedError("Simulated execution cancelled.")
                time.sleep(duration_ms / checkpoints / 1000)
                self._provider_progress(
                    execution_id, step["key"], checkpoint / checkpoints,
                    f"Simulated workflow progress {int(checkpoint / checkpoints * 100)}%.",
                )
            files = []
            for binding in configuration.get("output_bindings", []):
                files.append({
                    "node_id": str(binding.get("node_id")),
                    "type": "simulated",
                    "filename": f"simulated-{execution_id}-{binding.get('module_output_key') or 'output'}.png",
                    "preview_url": simulation.get("preview_url"),
                })
            result = {
                "workflow_preview": workflow, "engine": engine.value,
                "execution_mode": "simulated", "files": files,
                "simulation": {"duration_ms": duration_ms, "checkpoints": checkpoints},
            }
            return self._map_workflow_outputs(configuration, files, result)
        timeout = int(configuration.get("timeout_seconds") or 900)
        if engine == GenerationExecutionEngine.LOCAL_DOCKER:
            queued = comfyui_local_adapter_service.queue_prompt(workflow=workflow)
            with self._lock:
                self._provider_refs[execution_id] = {"engine": engine.value, "prompt_id": queued["prompt_id"], "client_id": queued["client_id"]}
            result = comfyui_local_adapter_service.execute_queued_prompt(
                prompt_id=queued["prompt_id"], client_id=queued["client_id"], job_public_id=str(execution_id),
                timeout_seconds=timeout, download_outputs=True,
                progress_callback=lambda progress, message, meta=None: self._provider_progress(execution_id, step["key"], progress, message),
            )
            return self._map_workflow_outputs(configuration, result.get("outputs") or [], result)
        payload = {
            "generation_module": {"step_key": step["key"], "workflow": workflow, "output_bindings": configuration.get("output_bindings", [])},
            "inputs": context,
        }
        submitted = runpod_serverless_adapter_service.submit_job(db, input_data=payload)
        with self._lock:
            self._provider_refs[execution_id] = {"engine": engine.value, "provider_job_id": submitted["provider_job_id"], "endpoint_id": submitted["endpoint_id"]}
        result = runpod_serverless_adapter_service.execute_submitted_job(
            db, provider_job_id=submitted["provider_job_id"], endpoint_id=submitted["endpoint_id"], job_public_id=str(execution_id),
            timeout_seconds=timeout, download_outputs=True,
            progress_callback=lambda progress, message, meta=None: self._provider_progress(execution_id, step["key"], progress, message),
            cancellation_callback=lambda: self.get(execution_id).cancel_requested,
        )
        files = result.get("files") or []
        return self._map_workflow_outputs(configuration, files, result)

    def _provider_progress(self, execution_id: UUID, step_key: str, progress: float, message: str) -> None:
        with self._lock:
            item = self._items.get(execution_id)
            if not item:
                return
            item.progress = min(89, max(item.progress, int(progress * 0.85)))
            item.logs.append(GenerationModuleExecutionLog(timestamp=utc_now(), step_key=step_key, message=message))

    @staticmethod
    def _prepare_workflow(step: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        configuration = copy.deepcopy(step.get("configuration") or {})
        workflow = configuration.get("workflow")
        if not isinstance(workflow, dict):
            raise AppException(f"Workflow step '{step['key']}' has no workflow JSON.")
        for binding in configuration.get("input_bindings", []):
            source_key = binding.get("module_input_key")
            value = context.get(source_key)
            node = workflow.get(str(binding.get("node_id")))
            if not isinstance(node, dict):
                raise AppException(f"Workflow node '{binding.get('node_id')}' was not found.")
            node.setdefault("inputs", {})[binding["input_field"]] = value
        return workflow, configuration

    @staticmethod
    def _map_workflow_outputs(configuration: dict[str, Any], files: list[dict[str, Any]], raw: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {"files": files, "provider_result": raw}
        for binding in configuration.get("output_bindings", []):
            key = binding.get("module_output_key")
            node_id = str(binding.get("node_id"))
            matched = [item for item in files if str(item.get("node_id")) == node_id]
            if key:
                result[key] = matched[0] if len(matched) == 1 else matched
        return result

    @staticmethod
    def _execute_python(step: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        configuration = step.get("configuration") or {}
        source = configuration.get("source_code") or ""
        entrypoint = configuration.get("entrypoint") or "run"
        timeout = int(configuration.get("timeout_seconds") or 300)
        safe_builtins = MappingProxyType({
            "len": len, "min": min, "max": max, "sum": sum, "sorted": sorted, "range": range,
            "enumerate": enumerate, "zip": zip, "str": str, "int": int, "float": float,
            "bool": bool, "dict": dict, "list": list, "tuple": tuple, "set": set,
            "abs": abs, "round": round, "any": any, "all": all, "isinstance": isinstance,
            "Exception": Exception, "ValueError": ValueError,
        })
        namespace: dict[str, Any] = {"__builtins__": safe_builtins, "json": json}
        exec(compile(source, f"generation_module_{step['key']}.py", "exec"), namespace, namespace)
        function = namespace.get(entrypoint)
        if not callable(function):
            raise AppException(f"Python entrypoint '{entrypoint}' was not found.")
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(function, copy.deepcopy(context))
            try:
                result = future.result(timeout=timeout)
            except FutureTimeoutError as exc:
                raise AppException(f"Python step '{step['key']}' exceeded {timeout} seconds.") from exc
        if result is None:
            return {}
        return result if isinstance(result, dict) else {"result": result}

    @staticmethod
    def _resolve_module_outputs(definitions: list[dict[str, Any]], context: dict[str, Any]) -> dict[str, Any]:
        outputs: dict[str, Any] = {}
        for definition in sorted(definitions, key=lambda row: row["position"]):
            value: Any = context.get(definition.get("source_step_key")) if definition.get("source_step_key") else context
            path = definition.get("source_path")
            if path:
                for part in path.split("."):
                    value = value.get(part) if isinstance(value, dict) else None
            if value is None:
                value = context.get(definition["key"])
            outputs[definition["key"]] = value
        return outputs


generation_module_runtime_service = GenerationModuleRuntimeService()
