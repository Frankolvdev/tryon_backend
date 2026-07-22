from __future__ import annotations

import copy
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime
from types import MappingProxyType
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.common.exceptions import AppException, NotFoundException
from app.common.generation_module_enums import GenerationExecutionEngine, GenerationModuleStepType
from app.common.time import utc_now
from app.schemas.generation_module_runtime import (
    GenerationModuleExecutionCreate,
    GenerationModuleExecutionLog,
    GenerationModuleExecutionResponse,
    GenerationModuleStepExecution,
)
from app.services.generation_module_service import generation_module_service


class GenerationModuleRuntimeService:
    def __init__(self) -> None:
        self._items: dict[UUID, GenerationModuleExecutionResponse] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="generation-module")

    def create(self, db: Session, *, module_id: int, data: GenerationModuleExecutionCreate) -> GenerationModuleExecutionResponse:
        module = generation_module_service.get_response(db, module_id=module_id)
        if not module.is_active:
            raise AppException("The generation module is inactive.")
        self._validate_inputs(module.inputs, data.inputs)
        engine = data.engine or module.default_execution_engine
        now = utc_now()
        execution = GenerationModuleExecutionResponse(
            id=uuid4(), module_id=module.id, module_key=module.key, engine=engine,
            status="queued", progress=0, inputs=copy.deepcopy(data.inputs), context=copy.deepcopy(data.inputs),
            outputs={}, steps=[GenerationModuleStepExecution(step_key=s.key, step_name=s.name, step_type=s.step_type, status="pending") for s in sorted(module.steps, key=lambda item: item.position) if s.is_enabled],
            logs=[GenerationModuleExecutionLog(timestamp=now, message="Execution queued.")],
            created_at=now,
        )
        with self._lock:
            self._items[execution.id] = execution
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

    def cancel(self, execution_id: UUID) -> GenerationModuleExecutionResponse:
        with self._lock:
            item = self._items.get(execution_id)
            if not item:
                raise NotFoundException("Generation module execution not found.")
            if item.status in {"completed", "failed", "cancelled"}:
                return item.model_copy(deep=True)
            item.cancel_requested = True
            item.logs.append(GenerationModuleExecutionLog(timestamp=utc_now(), level="warning", message="Cancellation requested."))
            return item.model_copy(deep=True)

    def _run(self, execution_id: UUID, module: dict[str, Any]) -> None:
        started = utc_now()
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
                        item.status = "cancelled"; item.progress = min(item.progress, 99)
                        item.logs.append(GenerationModuleExecutionLog(timestamp=utc_now(), level="warning", message="Execution cancelled."))
                        break
                    state = item.steps[index]
                    state.status = "running"; state.started_at = utc_now()
                    item.logs.append(GenerationModuleExecutionLog(timestamp=state.started_at, step_key=step["key"], message=f"Step '{step['name']}' started."))
                    context = copy.deepcopy(item.context)
                outputs = self._execute_step(step, context, self._items[execution_id].engine)
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
        except Exception as exc:
            with self._lock:
                item = self._items[execution_id]
                item.status = "failed"; item.error = str(exc)
                running = next((s for s in item.steps if s.status == "running"), None)
                if running:
                    running.status = "failed"; running.error = str(exc); running.finished_at = utc_now()
                item.logs.append(GenerationModuleExecutionLog(timestamp=utc_now(), level="error", step_key=running.step_key if running else None, message=str(exc)))
        finally:
            finished = utc_now()
            with self._lock:
                item = self._items[execution_id]; item.finished_at = finished
                item.duration_ms = int((finished - started).total_seconds() * 1000)

    def _execute_step(self, step: dict[str, Any], context: dict[str, Any], engine: GenerationExecutionEngine) -> dict[str, Any]:
        if step["step_type"] == GenerationModuleStepType.PYTHON.value:
            return self._execute_python(step, context)
        if step["step_type"] == GenerationModuleStepType.WORKFLOW.value:
            return self._prepare_workflow(step, context, engine)
        raise AppException(f"Unsupported generation module step type: {step['step_type']}")

    @staticmethod
    def _prepare_workflow(step: dict[str, Any], context: dict[str, Any], engine: GenerationExecutionEngine) -> dict[str, Any]:
        configuration = copy.deepcopy(step.get("configuration") or {})
        workflow = configuration.get("workflow")
        if not isinstance(workflow, dict):
            raise AppException(f"Workflow step '{step['key']}' has no workflow JSON.")
        for binding in configuration.get("input_bindings", []):
            value = context.get(binding["module_input_key"])
            node = workflow.get(str(binding["node_id"]))
            if not isinstance(node, dict):
                raise AppException(f"Workflow node '{binding['node_id']}' was not found.")
            node.setdefault("inputs", {})[binding["input_field"]] = value
        # Until Docker/RunPod connectors are enabled, workflow steps return a deterministic preview.
        time.sleep(0.15)
        return {
            "workflow_preview": workflow,
            "workflow_name": configuration.get("workflow_name") or step["name"],
            "engine": engine.value,
            "output_bindings": configuration.get("output_bindings", []),
            "execution_mode": "prepared" if engine != GenerationExecutionEngine.SIMULATED else "simulated",
        }

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
        if not isinstance(result, dict):
            return {"result": result}
        return result

    @staticmethod
    def _resolve_module_outputs(definitions: list[dict[str, Any]], context: dict[str, Any]) -> dict[str, Any]:
        outputs: dict[str, Any] = {}
        for definition in sorted(definitions, key=lambda row: row["position"]):
            value: Any = context
            if definition.get("source_step_key"):
                value = context.get(definition["source_step_key"])
            path = definition.get("source_path")
            if path:
                for part in path.split("."):
                    if isinstance(value, dict):
                        value = value.get(part)
                    else:
                        value = None; break
            if value is None:
                value = context.get(definition["key"])
            outputs[definition["key"]] = value
        return outputs


generation_module_runtime_service = GenerationModuleRuntimeService()
