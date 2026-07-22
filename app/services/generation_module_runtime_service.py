from __future__ import annotations

import copy
import io
import json
import threading
import time
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
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
from app.services.generation_module_file_materializer_service import generation_module_file_materializer_service
from app.services.generation_module_security_service import generation_module_security_service
from app.services.generation_module_execution_store_service import generation_module_execution_store_service
from app.services.generation_module_billing_service import generation_module_billing_service
from app.services.generation_module_result_service import generation_module_result_service
from app.services.storage_service import storage_service
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
        if user_id is not None:
            generation_module_security_service.ensure_user_can_start(self, user_id=user_id, engine=engine)
        now = utc_now()
        execution_id = uuid4()
        pricing = module.pricing
        if user_id is not None and (pricing is None or not pricing.is_active):
            raise AppException("The generation module has no active pricing rule.")
        tokens = int(pricing.required_tokens) if pricing and user_id is not None else 0
        if user_id is not None and tokens > 0:
            generation_module_billing_service.charge(
                db, user_id=user_id, execution_id=str(execution_id), module_key=module.key, tokens=tokens
            )
        execution = GenerationModuleExecutionResponse(
            id=execution_id, module_id=module.id, module_key=module.key, user_id=user_id, engine=engine,
            status="queued", progress=0, inputs=copy.deepcopy(data.inputs), context=copy.deepcopy(data.inputs),
            outputs={}, steps=[GenerationModuleStepExecution(step_key=s.key, step_name=s.name, step_type=s.step_type, status="pending") for s in sorted(module.steps, key=lambda item: item.position) if s.is_enabled],
            logs=[GenerationModuleExecutionLog(timestamp=now, message=(f"Execution queued. {tokens} tokens charged." if tokens else "Execution queued."))], created_at=now,
            pricing_rule_id=(pricing.id if pricing else None), tokens_charged=tokens,
            currency=(pricing.currency if pricing else None),
            commercial_price=(pricing.final_price_usd if pricing else None),
        )
        with self._lock:
            self._items[execution.id] = execution
            self._owners[execution.id] = user_id
        generation_module_execution_store_service.save(execution)
        self._executor.submit(self._run, execution.id, module.model_dump(mode="python"))
        return self.get(execution.id)

    @staticmethod
    def _validate_inputs(definitions: list[Any], values: dict[str, Any]) -> None:
        allowed_keys = {item.key for item in definitions}
        unknown = sorted(set(values) - allowed_keys)
        if unknown:
            raise AppException(f"Unknown module inputs: {', '.join(unknown)}.")
        for item in definitions:
            value = values.get(item.key, item.default_value)
            if item.is_required and (value is None or value == ""):
                raise AppException(f"Required module input '{item.key}' is missing.")
            if value is None:
                continue
            rules = item.validation or {}
            if item.input_type in {"integer", "float"}:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise AppException(f"Module input '{item.key}' must be numeric.")
                if "min" in rules and value < rules["min"]:
                    raise AppException(f"Module input '{item.key}' is below its minimum.")
                if "max" in rules and value > rules["max"]:
                    raise AppException(f"Module input '{item.key}' exceeds its maximum.")
            if item.input_type in {"text", "textarea"}:
                if not isinstance(value, str):
                    raise AppException(f"Module input '{item.key}' must be text.")
                if "min_length" in rules and len(value) < rules["min_length"]:
                    raise AppException(f"Module input '{item.key}' is shorter than allowed.")
                if "max_length" in rules and len(value) > rules["max_length"]:
                    raise AppException(f"Module input '{item.key}' is longer than allowed.")
            if item.input_type == "select":
                options = rules.get("options") or []
                allowed = {str(option.get("value")) if isinstance(option, dict) else str(option) for option in options}
                if str(value) not in allowed:
                    raise AppException(f"Module input '{item.key}' has an invalid option.")
            if item.input_type == "boolean" and not isinstance(value, bool):
                raise AppException(f"Module input '{item.key}' must be boolean.")
            if item.input_type == "json" and not isinstance(value, (dict, list)):
                raise AppException(f"Module input '{item.key}' must contain JSON data.")
            if item.input_type in {"image", "file"}:
                if not isinstance(value, dict) or not value.get("__generation_file__"):
                    raise AppException(f"Module input '{item.key}' must contain an uploaded file.")

    def get(self, execution_id: UUID) -> GenerationModuleExecutionResponse:
        with self._lock:
            item = self._items.get(execution_id)
            if item:
                return item.model_copy(deep=True)
        persisted = generation_module_execution_store_service.get(execution_id)
        if persisted is None:
            raise NotFoundException("Generation module execution not found.")
        if (
            persisted.status == "failed"
            and persisted.user_id is not None
            and persisted.tokens_charged > 0
            and not persisted.tokens_refunded
            and (persisted.error or "").startswith("Execution was interrupted because the backend process restarted")
        ):
            db = SessionLocal()
            try:
                refunded = generation_module_billing_service.refund(
                    db,
                    user_id=persisted.user_id,
                    execution_id=str(persisted.id),
                    module_key=persisted.module_key,
                    tokens=persisted.tokens_charged,
                    reason=persisted.error or "backend restart",
                )
                if refunded:
                    persisted.tokens_refunded = True
                    persisted.logs.append(GenerationModuleExecutionLog(
                        timestamp=utc_now(),
                        message=f"{persisted.tokens_charged} tokens refunded after backend restart.",
                    ))
                    generation_module_execution_store_service.save(persisted)
            finally:
                db.close()
        return persisted


    def get_for_user(self, execution_id: UUID, *, user_id: int) -> GenerationModuleExecutionResponse:
        item = self.get(execution_id)
        if item.user_id != user_id:
            raise NotFoundException("Generation module execution not found.")
        return item

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
            snapshot = item.model_copy(deep=True)
            provider = copy.deepcopy(self._provider_refs.get(execution_id) or {})
        generation_module_execution_store_service.save(snapshot)
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
            running_snapshot = item.model_copy(deep=True)
        generation_module_execution_store_service.save(running_snapshot)
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
                    step_snapshot = item.model_copy(deep=True)
                generation_module_execution_store_service.save(step_snapshot)
            with self._lock:
                item = self._items[execution_id]
                if item.status != "cancelled":
                    resolved_outputs = self._resolve_module_outputs(module["outputs"], item.context)
                    item.outputs = self._persist_final_outputs(
                        db, execution_id=execution_id, user_id=item.user_id, outputs=resolved_outputs
                    )
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
            finished = utc_now()
            with self._lock:
                item = self._items[execution_id]; item.finished_at = finished
                item.duration_ms = int((finished - started).total_seconds() * 1000)
                self._provider_refs.pop(execution_id, None)
                should_refund = item.status in {"failed", "cancelled"} and item.user_id is not None and item.tokens_charged > 0
                refund_reason = item.error or item.status
            if should_refund:
                try:
                    refunded = generation_module_billing_service.refund(
                        db, user_id=item.user_id, execution_id=str(item.id), module_key=item.module_key,
                        tokens=item.tokens_charged, reason=refund_reason,
                    )
                    if refunded:
                        with self._lock:
                            item.tokens_refunded = True
                            item.logs.append(GenerationModuleExecutionLog(
                                timestamp=utc_now(), message=f"{item.tokens_charged} tokens refunded automatically."
                            ))
                except Exception as refund_error:
                    db.rollback()
                    with self._lock:
                        item.logs.append(GenerationModuleExecutionLog(
                            timestamp=utc_now(), level="error", message=f"Automatic token refund failed: {refund_error}"
                        ))
            with self._lock:
                final_snapshot = item.model_copy(deep=True)
            db.close()
            generation_module_execution_store_service.save(final_snapshot)

    def _execute_step(self, db: Session, execution_id: UUID, step: dict[str, Any], context: dict[str, Any], engine: GenerationExecutionEngine) -> dict[str, Any]:
        if step["step_type"] == GenerationModuleStepType.PYTHON.value:
            return self._execute_python(db, execution_id, step, context)
        if step["step_type"] != GenerationModuleStepType.WORKFLOW.value:
            raise AppException(f"Unsupported generation module step type: {step['step_type']}")
        workflow, configuration, engine_files = self._prepare_workflow(db, execution_id, step, context, engine)
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
                "workflow_preview": workflow, "engine": engine.value, "materialized_inputs": engine_files,
                "execution_mode": "simulated", "files": files,
                "simulation": {"duration_ms": duration_ms, "checkpoints": checkpoints},
            }
            return self._map_workflow_outputs(configuration, files, result)
        timeout = int(configuration.get("timeout_seconds") or 900)
        if engine == GenerationExecutionEngine.LOCAL_DOCKER:
            queued = comfyui_local_adapter_service.queue_prompt(workflow=workflow, extra_data={"generation_execution_id": str(execution_id), "materialized_inputs": engine_files})
            with self._lock:
                self._provider_refs[execution_id] = {"engine": engine.value, "prompt_id": queued["prompt_id"], "client_id": queued["client_id"]}
            result = comfyui_local_adapter_service.execute_queued_prompt(
                prompt_id=queued["prompt_id"], client_id=queued["client_id"], job_public_id=str(execution_id),
                timeout_seconds=timeout, download_outputs=True,
                progress_callback=lambda progress, message, meta=None: self._provider_progress(execution_id, step["key"], progress, message),
            )
            owner_id = self.get(execution_id).user_id
            files = self._mark_temporary_files(result.get("outputs") or [])
            result["outputs"] = files
            return self._map_workflow_outputs(configuration, files, result)
        payload = {
            "generation_module": {"step_key": step["key"], "workflow": workflow, "output_bindings": configuration.get("output_bindings", [])},
            "inputs": context,
            "files": engine_files,
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
        owner_id = self.get(execution_id).user_id
        files = self._mark_temporary_files(result.get("files") or [])
        result["files"] = files
        return self._map_workflow_outputs(configuration, files, result)

    def _provider_progress(self, execution_id: UUID, step_key: str, progress: float, message: str) -> None:
        with self._lock:
            item = self._items.get(execution_id)
            if not item:
                return
            item.progress = min(89, max(item.progress, int(progress * 0.85)))
            item.logs.append(GenerationModuleExecutionLog(timestamp=utc_now(), step_key=step_key, message=message))
            progress_snapshot = item.model_copy(deep=True)
        generation_module_execution_store_service.save(progress_snapshot)

    def _prepare_workflow(
        self,
        db: Session,
        execution_id: UUID,
        step: dict[str, Any],
        context: dict[str, Any],
        engine: GenerationExecutionEngine,
    ) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        configuration = copy.deepcopy(step.get("configuration") or {})
        workflow = configuration.get("workflow")
        if not isinstance(workflow, dict):
            raise AppException(f"Workflow step '{step['key']}' has no workflow JSON.")
        materialized: list[dict[str, Any]] = []
        cache: dict[str, dict[str, Any]] = {}
        for binding in configuration.get("input_bindings", []):
            source_key = binding.get("source_path") or binding.get("module_input_key")
            value = context
            for part in str(source_key or "").split("."):
                value = value.get(part) if isinstance(value, dict) else None
            node = workflow.get(str(binding.get("node_id")))
            if not isinstance(node, dict):
                raise AppException(f"Workflow node '{binding.get('node_id')}' was not found.")
            if isinstance(value, dict) and self._is_generation_file_reference(value):
                cached = cache.get(str(source_key))
                if cached is None:
                    if engine == GenerationExecutionEngine.LOCAL_DOCKER:
                        cached = generation_module_file_materializer_service.materialize_local(
                            db, execution_id=execution_id, module_input_key=str(source_key), reference=value
                        )
                    elif engine == GenerationExecutionEngine.RUNPOD_SERVERLESS:
                        cached = generation_module_file_materializer_service.materialize_runpod(
                            db, execution_id=execution_id, module_input_key=str(source_key), reference=value
                        )
                    else:
                        cached = {
                            "module_input_key": str(source_key),
                            "engine": "simulated",
                            "relative_name": value.get("filename") or source_key,
                        }
                    cache[str(source_key)] = cached
                    materialized.append(cached)
                value = cached.get("relative_name") or cached.get("target_name") or cached.get("filename")
            node.setdefault("inputs", {})[binding["input_field"]] = value
        return workflow, configuration, materialized


    @staticmethod
    def _is_generation_file_reference(value: Any) -> bool:
        return isinstance(value, dict) and bool(
            value.get("__generation_file__")
            or value.get("storage_file_id")
            or value.get("local_path")
        )

    @staticmethod
    def _mark_temporary_files(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
        marked: list[dict[str, Any]] = []
        for item in files:
            enriched = dict(item)
            if enriched.get("local_path") or enriched.get("storage_file_id"):
                enriched["__generation_file__"] = True
                if not enriched.get("storage_file_id"):
                    enriched["temporary"] = True
            marked.append(enriched)
        return marked

    def _persist_final_outputs(
        self,
        db: Session,
        *,
        execution_id: UUID,
        user_id: int | None,
        outputs: dict[str, Any],
    ) -> dict[str, Any]:
        def persist(value: Any) -> Any:
            if self._is_generation_file_reference(value):
                if value.get("storage_file_id"):
                    final = dict(value)
                else:
                    registered = generation_module_result_service.register_files(
                        db, execution_id=execution_id, user_id=user_id, files=[dict(value)]
                    )
                    final = registered[0] if registered else dict(value)
                final.pop("temporary", None)
                final["__generation_file__"] = True
                return final
            if isinstance(value, dict):
                return {key: persist(item) for key, item in value.items()}
            if isinstance(value, list):
                return [persist(item) for item in value]
            return value

        return {key: persist(value) for key, value in outputs.items()}

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

    def _execute_python(
        self,
        db: Session,
        execution_id: UUID,
        step: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        configuration = step.get("configuration") or {}
        source = configuration.get("source_code") or ""
        entrypoint = configuration.get("entrypoint") or "run"
        timeout = int(configuration.get("timeout_seconds") or 300)

        mapped_inputs: dict[str, Any] = {}
        for input_key, source_path in (step.get("input_mapping") or {}).items():
            value: Any = context
            for part in str(source_path or "").split("."):
                if not part:
                    continue
                value = value.get(part) if isinstance(value, dict) else None
            mapped_inputs[str(input_key)] = value

        raw_inputs = mapped_inputs if mapped_inputs else copy.deepcopy(context)

        # Python image ports receive real Pillow images instead of the internal
        # persisted-file reference used by the API and workflow runtime.
        def materialize(value: Any) -> Any:
            if isinstance(value, dict) and self._is_generation_file_reference(value):
                try:
                    from PIL import Image
                except ImportError as exc:
                    raise AppException(
                        "Pillow is required to use image inputs in Python nodes."
                    ) from exc
                content, _filename, content_type = (
                    generation_module_file_materializer_service._read_bytes(db, value)
                )
                if not str(content_type or "").startswith("image/"):
                    return value
                image = Image.open(io.BytesIO(content))
                image.load()
                return image
            if isinstance(value, dict):
                return {key: materialize(item) for key, item in value.items()}
            if isinstance(value, list):
                return [materialize(item) for item in value]
            return value

        python_inputs = materialize(raw_inputs)

        # CPython requires a real dict for frame builtins. MappingProxyType can
        # trigger ``dictobject.c: bad argument to internal function`` while
        # executing user functions, especially when an import is present.
        allowed_import_roots = {"PIL", "math", "json", "io", "base64"}
        real_import = __import__

        def safe_import(name: str, globals=None, locals=None, fromlist=(), level=0):
            root = name.split(".", 1)[0]
            if root not in allowed_import_roots:
                raise ImportError(f"Import '{name}' is not allowed in Python nodes.")
            return real_import(name, globals, locals, fromlist, level)

        safe_builtins: dict[str, Any] = {
            "len": len, "min": min, "max": max, "sum": sum, "sorted": sorted, "range": range,
            "enumerate": enumerate, "zip": zip, "str": str, "int": int, "float": float,
            "bool": bool, "dict": dict, "list": list, "tuple": tuple, "set": set,
            "abs": abs, "round": round, "any": any, "all": all, "isinstance": isinstance,
            "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
            "ImportError": ImportError, "__import__": safe_import,
        }
        namespace: dict[str, Any] = {"__builtins__": safe_builtins, "json": json}
        exec(compile(source, f"generation_module_{step['key']}.py", "exec"), namespace, namespace)
        function = namespace.get(entrypoint)
        if not callable(function):
            raise AppException(f"Python entrypoint '{entrypoint}' was not found.")

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(function, python_inputs)
            try:
                result = future.result(timeout=timeout)
            except FutureTimeoutError as exc:
                raise AppException(f"Python step '{step['key']}' exceeded {timeout} seconds.") from exc

        raw_result: dict[str, Any]
        if result is None:
            raw_result = {}
        else:
            raw_result = result if isinstance(result, dict) else {"result": result}

        # Convert Pillow outputs back into persisted, JSON-safe generation-file
        # references so they can be consumed by later Workflow/Python nodes.
        def persist(value: Any, key_path: str) -> Any:
            try:
                from PIL import Image
            except ImportError:
                Image = None  # type: ignore[assignment]
            if Image is not None and isinstance(value, Image.Image):
                image = value
                if image.mode not in {"RGB", "RGBA", "L"}:
                    image = image.convert("RGBA")
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                filename = f"{step['key']}-{key_path.replace('.', '-')}.png"
                runtime_dir = Path(tempfile.gettempdir()) / "tryon-generation-runtime" / str(execution_id)
                runtime_dir.mkdir(parents=True, exist_ok=True)
                local_path = runtime_dir / filename
                local_path.write_bytes(buffer.getvalue())
                return {
                    "__generation_file__": True,
                    "temporary": True,
                    "local_path": str(local_path),
                    "filename": filename,
                    "content_type": "image/png",
                    "size_bytes": local_path.stat().st_size,
                }
            if isinstance(value, dict):
                return {key: persist(item, f"{key_path}.{key}") for key, item in value.items()}
            if isinstance(value, list):
                return [persist(item, f"{key_path}.{index}") for index, item in enumerate(value)]
            if isinstance(value, (str, int, float, bool)) or value is None:
                return value
            raise AppException(
                f"Python output '{key_path}' returned unsupported type '{type(value).__name__}'."
            )

        raw_result = persist(raw_result, "result")
        output_mapping = step.get("output_mapping") or {}
        if not output_mapping:
            return raw_result

        mapped_result: dict[str, Any] = {}
        for output_key, result_path in output_mapping.items():
            value: Any = raw_result
            for part in str(result_path or output_key).split("."):
                if not part:
                    continue
                value = value.get(part) if isinstance(value, dict) else None
            mapped_result[str(output_key)] = value
        return mapped_result

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

# Persistent history helpers used by AppWeb and BackOffice.
def _runtime_list(self, *, user_id: int | None = None, module_id: int | None = None, status: str | None = None, skip: int = 0, limit: int = 100):
    persisted, _ = generation_module_execution_store_service.list(
        user_id=user_id, module_id=module_id, status=status, skip=0, limit=10000
    )
    with self._lock:
        active = [item.model_copy(deep=True) for item in self._items.values()]
    merged = {item.id: item for item in persisted}
    for item in active:
        if user_id is not None and item.user_id != user_id:
            continue
        if module_id is not None and item.module_id != module_id:
            continue
        if status and item.status != status:
            continue
        merged[item.id] = item
    items = sorted(merged.values(), key=lambda item: item.created_at, reverse=True)
    return items[skip:skip + limit], len(items)


def _runtime_retry(self, db: Session, execution_id: UUID, *, user_id: int | None = None, engine=None):
    current = self.get_for_user(execution_id, user_id=user_id) if user_id is not None else self.get(execution_id)
    payload = GenerationModuleExecutionCreate(inputs=copy.deepcopy(current.inputs), engine=engine or current.engine)
    return self.create(db, module_id=current.module_id, data=payload, user_id=user_id)


def _runtime_delete(self, execution_id: UUID, *, user_id: int | None = None):
    if user_id is not None:
        self.get_for_user(execution_id, user_id=user_id)
    else:
        self.get(execution_id)
    with self._lock:
        self._items.pop(execution_id, None)
        self._owners.pop(execution_id, None)
        self._provider_refs.pop(execution_id, None)
    generation_module_execution_store_service.delete(execution_id)


GenerationModuleRuntimeService.list = _runtime_list
GenerationModuleRuntimeService.retry = _runtime_retry
GenerationModuleRuntimeService.delete = _runtime_delete
