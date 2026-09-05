from __future__ import annotations

import base64
import copy
import io
import json
import hashlib
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin
from uuid import uuid4

import httpx
from PIL import Image

from .context import GenerationRuntimeContext
from .metrics import RuntimeMetricsCollector


VRAM_PURGE_SOURCE_MARKER = "TRYON_BUILTIN_COMFYUI_VRAM_PURGE_PASSTHROUGH_V1"


def _ordered_enabled_steps(module: dict[str, Any]) -> list[dict[str, Any]]:
    """Return enabled steps in dependency-safe order.

    Connections are authoritative. Persisted ``position`` is only a stable
    tie-breaker for independent branches, so stale DB positions can never run
    a consumer before the step that produces its input.
    """
    steps = [step for step in (module.get("steps") or []) if step.get("is_enabled")]
    by_key = {str(step.get("key") or ""): step for step in steps}
    order_key = lambda step: (int(step.get("position") or 0), str(step.get("key") or ""))
    dependencies: dict[str, set[str]] = {key: set() for key in by_key}

    def add_source(target_key: str, raw_path: Any) -> None:
        if not isinstance(raw_path, str) or "." not in raw_path:
            return
        source_key = raw_path.split(".", 1)[0]
        if source_key in by_key and source_key != target_key:
            dependencies[target_key].add(source_key)

    for key, step in by_key.items():
        for raw_path in (step.get("input_mapping") or {}).values():
            add_source(key, raw_path)
        configuration = step.get("configuration") or {}
        for binding in configuration.get("input_bindings") or []:
            if isinstance(binding, dict):
                add_source(key, binding.get("source_path") or binding.get("module_input_key"))

    dependents: dict[str, set[str]] = {key: set() for key in by_key}
    indegree = {key: len(value) for key, value in dependencies.items()}
    for target_key, source_keys in dependencies.items():
        for source_key in source_keys:
            dependents[source_key].add(target_key)

    ready = sorted((key for key, degree in indegree.items() if degree == 0), key=lambda key: order_key(by_key[key]))
    ordered: list[dict[str, Any]] = []
    while ready:
        key = ready.pop(0)
        ordered.append(by_key[key])
        for target_key in sorted(dependents[key], key=lambda item: order_key(by_key[item])):
            indegree[target_key] -= 1
            if indegree[target_key] == 0:
                ready.append(target_key)
                ready.sort(key=lambda item: order_key(by_key[item]))

    if len(ordered) != len(steps):
        blocked = sorted(key for key, degree in indegree.items() if degree > 0)
        raise ValueError(f"Generation module contains a cyclic step dependency: {', '.join(blocked)}")
    return ordered


class GenerationRuntime:
    CONTRACT = "tryon.generation-runtime/v1"

    def __init__(self, *, comfy_url: str | None = None) -> None:
        self.comfy_url = (comfy_url or os.getenv("COMFYUI_URL") or "http://127.0.0.1:8188").rstrip("/")
        self.root = Path(os.getenv("GENERATION_RUNTIME_DIR") or tempfile.gettempdir()) / "tryon-runpod-runtime"
        self.root.mkdir(parents=True, exist_ok=True)
        self._comfy_object_info: dict[str, Any] | None = None

    def execute(self, payload: dict[str, Any], progress: Callable[[float, str], None] | None = None) -> dict[str, Any]:
        if payload.get("runtime_contract") != self.CONTRACT:
            raise ValueError("Unsupported Generation Runtime contract.")
        module = payload.get("module")
        context = self._materialize(copy.deepcopy(payload.get("context") or {}), self.root / str(payload.get("execution_id") or uuid4()))
        if not isinstance(module, dict):
            raise ValueError("Generation module payload is missing.")
        steps = _ordered_enabled_steps(module)

        # Diagnostic-only trace. This intentionally does not participate in
        # ordering, filtering, input resolution, execution, or context merge.
        # It reports what the remote runtime actually received and what the
        # already-existing dependency sorter selected.
        raw_steps = module.get("steps") or []
        ordered_keys = [str(item.get("key") or "") for item in steps]
        diagnostic_steps: list[dict[str, Any]] = []
        for raw_index, item in enumerate(raw_steps):
            if not isinstance(item, dict):
                diagnostic_steps.append({"raw_index": raw_index, "invalid_step": True})
                continue
            configuration = item.get("configuration") or {}
            source = str(configuration.get("source_code") or "")
            input_mapping = item.get("input_mapping") or {}
            workflow_bindings = configuration.get("input_bindings") or []
            dependency_sources: set[str] = set()
            for raw_path in input_mapping.values() if isinstance(input_mapping, dict) else []:
                if isinstance(raw_path, str) and "." in raw_path:
                    dependency_sources.add(raw_path.split(".", 1)[0])
            for binding in workflow_bindings if isinstance(workflow_bindings, list) else []:
                if not isinstance(binding, dict):
                    continue
                raw_path = binding.get("source_path") or binding.get("module_input_key")
                if isinstance(raw_path, str) and "." in raw_path:
                    dependency_sources.add(raw_path.split(".", 1)[0])
            key = str(item.get("key") or "")
            diagnostic_steps.append(
                {
                    "raw_index": raw_index,
                    "key": key,
                    "position": item.get("position"),
                    "step_type": item.get("step_type"),
                    "is_enabled": item.get("is_enabled"),
                    "selected_for_execution": key in ordered_keys,
                    "execution_index": ordered_keys.index(key) if key in ordered_keys else None,
                    "vram_purge_marker": VRAM_PURGE_SOURCE_MARKER in source,
                    "dependencies": sorted(dependency_sources),
                    "input_mapping": input_mapping if isinstance(input_mapping, dict) else {},
                    "workflow_input_bindings": workflow_bindings if isinstance(workflow_bindings, list) else [],
                }
            )
        print(
            "[runtime-diagnostic] "
            + json.dumps(
                {
                    "event": "generation_step_plan",
                    "execution_id": payload.get("execution_id"),
                    "raw_step_count": len(raw_steps),
                    "ordered_enabled_keys": ordered_keys,
                    "steps": diagnostic_steps,
                },
                ensure_ascii=False,
                default=str,
            ),
            flush=True,
        )

        states: list[dict[str, Any]] = []
        metrics = RuntimeMetricsCollector()
        for index, step in enumerate(steps):
            started = time.monotonic()
            key = str(step.get("key") or f"step-{index + 1}")
            try:
                if progress:
                    progress((index / max(len(steps), 1)) * 100, f"Step '{key}' started.")
                step_type = str(step.get("step_type") or "")
                if step_type == "workflow":
                    outputs = self._workflow(step, context, payload.get("execution_id"))
                elif step_type == "python":
                    outputs = self._python(step, context, payload.get("execution_id"))
                elif step_type == "utility":
                    outputs = self._utility(step, context, payload.get("execution_id"))
                else:
                    raise ValueError(f"Unsupported generation module step type: {step_type}")
                GenerationRuntimeContext.merge_step_outputs(context, key, outputs)
                duration_ms = int((time.monotonic() - started) * 1000)
                metrics.add_step(step_key=key, step_type=step_type, duration_ms=duration_ms, status="completed")
                states.append({"step_key": key, "step_type": step_type, "status": "completed", "duration_ms": duration_ms, "outputs": copy.deepcopy(outputs)})
                if progress:
                    progress(((index + 1) / max(len(steps), 1)) * 100, f"Step '{key}' completed.")
            except Exception as exc:
                duration_ms = int((time.monotonic() - started) * 1000)
                metrics.add_step(step_key=key, step_type=str(step.get("step_type") or ""), duration_ms=duration_ms, status="failed")
                states.append({"step_key": key, "step_type": str(step.get("step_type") or ""), "status": "failed", "duration_ms": duration_ms, "outputs": {}, "error": str(exc)})
                return {"runtime_contract": self.CONTRACT, "status": "failed", "error": str(exc), "steps": states, "metrics": metrics.snapshot(status="failed", error=str(exc))}
        outputs = GenerationRuntimeContext.resolve_module_outputs(module.get("outputs") or [], context)
        transport_payload, transport_metrics = self._externalize_transport({
            "steps": states,
            "outputs": outputs,
            "context": context,
        })
        runtime_metrics = metrics.snapshot(status="completed")
        runtime_metrics.update(transport_metrics)
        return {
            "runtime_contract": self.CONTRACT,
            "status": "completed",
            "steps": transport_payload["steps"],
            "outputs": transport_payload["outputs"],
            "context": transport_payload["context"],
            "files": transport_payload["files"],
            "metrics": runtime_metrics,
        }

    def _materialize(self, value: Any, directory: Path) -> Any:
        if isinstance(value, dict) and value.get("__generation_file__"):
            directory.mkdir(parents=True, exist_ok=True)
            filename = Path(str(value.get("filename") or uuid4().hex)).name
            target = directory / filename
            if value.get("content_base64"):
                target.write_bytes(base64.b64decode(value["content_base64"]))
            elif value.get("source_url") or value.get("url"):
                with httpx.Client(timeout=300, follow_redirects=True) as client:
                    target.write_bytes(client.get(value.get("source_url") or value.get("url")).raise_for_status().content)
            else:
                raise ValueError("Remote file has no transport payload.")
            return {"__generation_file__": True, "local_path": str(target), "filename": filename, "content_type": value.get("content_type"), "size_bytes": target.stat().st_size}
        if isinstance(value, dict):
            return {k: self._materialize(v, directory) for k, v in value.items()}
        if isinstance(value, list):
            return [self._materialize(v, directory) for v in value]
        return value

    @staticmethod
    def _decode_workflow(value: Any) -> dict[str, Any]:
        decoded = value
        for _ in range(3):
            if not isinstance(decoded, str):
                break
            raw = decoded.strip()
            if not raw:
                break
            try:
                decoded = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Workflow JSON string is invalid: {exc.msg}.") from exc
        if not isinstance(decoded, dict):
            raise ValueError("Workflow must be a JSON object or a JSON string containing an object.")
        return decoded

    @staticmethod
    def _normalize_model_reference(value: str, category: str) -> str:
        raw = value.strip().replace("\\", "/")
        while "//" in raw:
            raw = raw.replace("//", "/")
        raw = raw.strip().lstrip("/")
        if len(raw) >= 2 and raw[1] == ":":
            raw = raw[2:].lstrip("/")
        lowered = raw.lower()
        category_lower = category.lower()
        markers = (f"/models/{category_lower}/", f"models/{category_lower}/", f"/{category_lower}/", f"{category_lower}/")
        normalized = raw
        for marker in markers:
            index = lowered.rfind(marker)
            if index >= 0:
                normalized = raw[index + len(marker):]
                break
        normalized = normalized.strip().lstrip("/")
        parts = [part for part in normalized.split("/") if part not in ("", ".")]
        if not parts or any(part == ".." for part in parts):
            raise ValueError(f"Invalid {category} model path '{value}'. Relative paths cannot be empty or contain '..'.")
        return "/".join(parts)

    @classmethod
    def _normalize_workflow_model_paths(cls, workflow: dict[str, Any]) -> dict[str, Any]:
        field_categories = {"lora_name": "loras", "ckpt_name": "checkpoints", "checkpoint_name": "checkpoints", "unet_name": "diffusion_models", "vae_name": "vae", "clip_name": "text_encoders", "text_encoder_name": "text_encoders", "diffusion_model": "diffusion_models", "diffusion_model_name": "diffusion_models"}
        class_categories = {"loraloader": "loras", "loraloadermodelonly": "loras", "checkpointloadersimple": "checkpoints", "unetloader": "diffusion_models", "vaeloader": "vae", "cliploader": "text_encoders", "dualcliploader": "text_encoders"}
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                continue
            class_type = str(node.get("class_type") or "").replace("_", "").lower()
            fallback_category = class_categories.get(class_type)
            for field, value in list(inputs.items()):
                if not isinstance(value, str):
                    continue
                category = field_categories.get(str(field).lower())
                if category is None and fallback_category and str(field).lower() in {"model_name", "model", "filename", "file_name"}:
                    category = fallback_category
                if category is None:
                    continue
                try:
                    inputs[field] = cls._normalize_model_reference(value, category)
                except ValueError as exc:
                    raise ValueError(f"Invalid model path in ComfyUI node {node_id}, field '{field}': {exc}") from exc
        return workflow

    def _get_comfy_object_info(self) -> dict[str, Any]:
        if self._comfy_object_info is None:
            with httpx.Client(timeout=60) as client:
                response = client.get(f"{self.comfy_url}/object_info")
                response.raise_for_status()
                data = response.json()
            if not isinstance(data, dict):
                raise ValueError("ComfyUI /object_info returned an invalid response.")
            self._comfy_object_info = data
        return self._comfy_object_info

    def _resolve_dynamic_node_types(self, workflow: dict[str, Any]) -> dict[str, Any]:
        dynamic_nodes = [
            (node_id, node)
            for node_id, node in workflow.items()
            if isinstance(node, dict)
            and str(node.get("class_type") or "").startswith("ExecutePython")
            and str((node.get("_meta") or {}).get("title") or "").strip().lower() == "execute python"
        ]
        if not dynamic_nodes:
            return workflow

        object_info = self._get_comfy_object_info()
        available = set(object_info)
        candidates = [name for name in available if name.startswith("ExecutePython")]

        for node_id, node in dynamic_nodes:
            current = str(node.get("class_type") or "")
            if current in available:
                continue

            compatible: list[str] = []
            node_inputs = set((node.get("inputs") or {}).keys())
            for candidate in candidates:
                info = object_info.get(candidate) or {}
                display_name = str(info.get("display_name") or "").strip().lower()
                required = set(((info.get("input") or {}).get("required") or {}).keys())
                if display_name and display_name != "execute python":
                    continue
                if {"code", "n_outputs"}.issubset(node_inputs) and not {"code", "n_outputs"}.issubset(required | node_inputs):
                    continue
                compatible.append(candidate)

            if len(compatible) != 1:
                raise ValueError(
                    f"Could not resolve dynamic Execute Python node '{current}' for ComfyUI node '{node_id}'. "
                    f"Available candidates: {compatible or candidates or ['none']}."
                )
            node["class_type"] = compatible[0]
            print(f"[runtime] Execute Python class remapped for node {node_id}: {current} -> {compatible[0]}")
        return workflow

    def _workflow(self, step: dict[str, Any], context: dict[str, Any], execution_id: Any) -> dict[str, Any]:
        config = copy.deepcopy(step.get("configuration") or {})
        workflow = self._decode_workflow(config.get("workflow"))
        for binding in config.get("input_bindings") or []:
            source = binding.get("source_path") or binding.get("module_input_key")
            value = GenerationRuntimeContext.resolve(context, str(source or ""))
            node = workflow.get(str(binding.get("node_id")))
            if not isinstance(node, dict):
                raise ValueError(f"Workflow node '{binding.get('node_id')}' was not found.")
            if isinstance(value, dict) and value.get("__generation_file__"):
                value = self._upload_input(Path(value["local_path"]), str(execution_id))
            node.setdefault("inputs", {})[binding["input_field"]] = value
        workflow = self._normalize_workflow_model_paths(workflow)
        workflow = self._resolve_dynamic_node_types(workflow)
        result = self._execute_comfy(workflow, int(config.get("timeout_seconds") or 900))
        files = result["files"]
        mapped: dict[str, Any] = {"files": files, "provider_result": {"prompt_id": result["prompt_id"]}}
        for binding in config.get("output_bindings") or []:
            key = binding.get("module_output_key")
            matched = [item for item in files if str(item.get("node_id")) == str(binding.get("node_id"))]
            if key:
                mapped[key] = matched[0] if len(matched) == 1 else matched
        return mapped

    def _upload_input(self, path: Path, execution_id: str) -> str:
        with httpx.Client(timeout=300) as client, path.open("rb") as handle:
            response = client.post(f"{self.comfy_url}/upload/image", files={"image": (path.name, handle)}, data={"type": "input", "subfolder": f"generation-modules/{execution_id}", "overwrite": "true"})
            response.raise_for_status()
            data = response.json()
        return "/".join(part for part in [data.get("subfolder"), data.get("name")] if part)

    def _execute_comfy(self, workflow: dict[str, Any], timeout: int) -> dict[str, Any]:
        client_id = uuid4().hex
        with httpx.Client(timeout=60) as client:
            response = client.post(f"{self.comfy_url}/prompt", json={"prompt": workflow, "client_id": client_id})
            if response.is_error:
                try:
                    detail = response.json()
                except ValueError:
                    detail = response.text
                raise ValueError(f"ComfyUI rejected the workflow ({response.status_code}): {detail}")
            prompt_id = response.json()["prompt_id"]
        started = time.monotonic()
        history = None
        while time.monotonic() - started < timeout:
            with httpx.Client(timeout=60) as client:
                data = client.get(f"{self.comfy_url}/history/{prompt_id}").raise_for_status().json()
            history = data.get(prompt_id)
            if history:
                break
            time.sleep(1)
        if not history:
            raise TimeoutError(f"ComfyUI workflow exceeded {timeout} seconds.")
        files = []
        for node_id, node_output in (history.get("outputs") or {}).items():
            for category in ("images", "gifs", "videos", "audio"):
                for item in node_output.get(category) or []:
                    params = {"filename": item.get("filename"), "subfolder": item.get("subfolder") or "", "type": item.get("type") or "output"}
                    with httpx.Client(timeout=300) as client:
                        content = client.get(f"{self.comfy_url}/view", params=params).raise_for_status().content
                    suffix = Path(str(item.get("filename") or ".bin")).suffix or ".bin"
                    target = self.root / f"{uuid4().hex}{suffix}"
                    target.write_bytes(content)
                    files.append({"__generation_file__": True, "local_path": str(target), "filename": item.get("filename") or target.name, "content_type": item.get("content_type"), "size_bytes": len(content), "node_id": str(node_id)})
        return {"prompt_id": prompt_id, "files": files, "history": history}

    @staticmethod
    def _resolve_utility_value(values: dict[str, Any], path: str | None) -> Any:
        if not path:
            return copy.deepcopy(values)
        value: Any = values
        for part in str(path).split("."):
            if not part:
                continue
            value = value.get(part) if isinstance(value, dict) else None
        return copy.deepcopy(value)

    @staticmethod
    def _utility_cleanup_workflow() -> dict[str, Any]:
        return {
            "tryon_stage_boundary_sentinel": {
                "class_type": "TryOn: StageBoundarySentinel",
                "inputs": {},
            },
            "tryon_full_vram_cleanup": {
                "class_type": "LayerUtility: PurgeVRAM V2",
                "inputs": {
                    "anything": ["tryon_stage_boundary_sentinel", 0],
                    "purge_cache": True,
                    "purge_models": True,
                },
            },
        }

    @staticmethod
    def _history_error(history: dict[str, Any] | None) -> str | None:
        if not isinstance(history, dict):
            return None
        status = history.get("status") or {}
        if not isinstance(status, dict):
            return None
        messages = status.get("messages") or []
        if status.get("status_str") == "error":
            return json.dumps(messages, ensure_ascii=False, default=str)
        for message in messages:
            if isinstance(message, list) and message and message[0] in {"execution_error", "execution_interrupted"}:
                return json.dumps(message, ensure_ascii=False, default=str)
        return None

    def _utility(self, step: dict[str, Any], context: dict[str, Any], execution_id: Any) -> dict[str, Any]:
        del execution_id
        config = step.get("configuration") or {}
        action = str(config.get("action") or "")
        if action != "comfyui_vram_purge":
            raise ValueError(f"Unsupported utility action: {action}")
        input_mapping = step.get("input_mapping") or {}
        required_ports = [
            str(port.get("id") or "")
            for port in (config.get("input_ports") or [])
            if isinstance(port, dict) and port.get("is_required", True)
        ]
        missing_ports = [port_id for port_id in required_ports if port_id and port_id not in input_mapping]
        if missing_ports:
            raise ValueError(
                f"Utility step '{step.get('key')}' has unconnected required input port(s): "
                + ", ".join(missing_ports)
            )
        raw_inputs = GenerationRuntimeContext.step_inputs(context, input_mapping)
        empty_required = [
            port_id
            for port_id in required_ports
            if raw_inputs.get(port_id) is None
        ]
        if empty_required:
            raise ValueError(
                f"Utility step '{step.get('key')}' received empty required input value(s): "
                + ", ".join(empty_required)
            )
        result = self._execute_comfy(
            self._utility_cleanup_workflow(),
            int(config.get("timeout_seconds") or 120),
        )
        error = self._history_error(result.get("history"))
        if error:
            raise RuntimeError(f"ComfyUI VRAM cleanup failed: {error}")

        return copy.deepcopy(raw_inputs)

    @staticmethod
    def _vram_purge_workflow() -> dict[str, Any]:
        return {
            "tryon_stage_boundary_sentinel": {
                "class_type": "TryOn: StageBoundarySentinel",
                "inputs": {},
            },
            "tryon_full_vram_cleanup": {
                "class_type": "LayerUtility: PurgeVRAM V2",
                "inputs": {
                    "anything": ["tryon_stage_boundary_sentinel", 0],
                    "purge_cache": True,
                    "purge_models": True,
                },
            },
        }

    def _python(self, step: dict[str, Any], context: dict[str, Any], execution_id: Any) -> dict[str, Any]:
        config = step.get("configuration") or {}
        source = config.get("source_code") or ""
        entrypoint = config.get("entrypoint") or "run"
        timeout = int(config.get("timeout_seconds") or 300)
        raw_inputs = GenerationRuntimeContext.step_inputs(context, step.get("input_mapping"))

        # Pipeline Utility deliberately reuses the proven Python step transport:
        # same input_mapping, ordering, enabled flag and context merge. The only
        # special behavior is the operation executed between input and output.
        if VRAM_PURGE_SOURCE_MARKER in source:
            print(f"[runtime] Pipeline Utility '{step.get('key')}' FULL VRAM purge started.", flush=True)
            self._execute_comfy(self._vram_purge_workflow(), timeout)
            print(f"[runtime] Pipeline Utility '{step.get('key')}' FULL VRAM purge completed.", flush=True)
            return copy.deepcopy(raw_inputs)

        inputs = self._to_images(raw_inputs)
        allowed = {"PIL", "math", "json", "io", "base64"}
        real_import = __import__

        def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name.split(".", 1)[0] not in allowed:
                raise ImportError(f"Import '{name}' is not allowed in Python nodes.")
            return real_import(name, globals, locals, fromlist, level)

        builtins = {"len": len, "min": min, "max": max, "sum": sum, "sorted": sorted, "range": range, "enumerate": enumerate, "zip": zip, "str": str, "int": int, "float": float, "bool": bool, "dict": dict, "list": list, "tuple": tuple, "set": set, "abs": abs, "round": round, "any": any, "all": all, "isinstance": isinstance, "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError, "ImportError": ImportError, "__import__": safe_import}
        ns = {"__builtins__": builtins, "json": json}
        exec(compile(source, f"generation_module_{step.get('key')}.py", "exec"), ns, ns)
        fn = ns.get(entrypoint)
        if not callable(fn):
            raise ValueError(f"Python entrypoint '{entrypoint}' was not found.")
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(fn, inputs)
            try:
                result = future.result(timeout=timeout)
            except FutureTimeoutError as exc:
                raise TimeoutError(f"Python step '{step.get('key')}' exceeded {timeout} seconds.") from exc
        result = {} if result is None else (result if isinstance(result, dict) else {"result": result})
        return self._save_images(result, self.root / str(execution_id), str(step.get("key")))

    def _to_images(self, value: Any) -> Any:
        if isinstance(value, dict) and value.get("__generation_file__") and str(value.get("content_type") or "").startswith("image/"):
            image = Image.open(value["local_path"])
            image.load()
            return image
        if isinstance(value, dict):
            return {k: self._to_images(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._to_images(v) for v in value]
        return value

    def _save_images(self, value: Any, directory: Path, prefix: str) -> Any:
        if isinstance(value, Image.Image):
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / f"{prefix}-{uuid4().hex[:10]}.png"
            image = value if value.mode in {"RGB", "RGBA", "L"} else value.convert("RGBA")
            image.save(target, "PNG")
            return {"__generation_file__": True, "local_path": str(target), "filename": target.name, "content_type": "image/png", "size_bytes": target.stat().st_size}
        if isinstance(value, dict):
            return {k: self._save_images(v, directory, prefix) for k, v in value.items()}
        if isinstance(value, list):
            return [self._save_images(v, directory, prefix) for v in value]
        return value

    def _externalize_transport(self, value: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        """Externalize generation files once and replace repetitions with file refs.

        The registry is provider/storage agnostic. Backend still owns persistence and
        storage selection; the remote runtime only deduplicates transport bytes.
        """
        files: dict[str, dict[str, Any]] = {}
        file_id_by_digest: dict[str, str] = {}
        path_content_cache: dict[str, tuple[bytes, str]] = {}
        occurrence_count = 0
        occurrence_declared_bytes = 0

        def externalize(item: Any) -> Any:
            nonlocal occurrence_count, occurrence_declared_bytes
            if isinstance(item, dict) and item.get("__generation_file__"):
                path = Path(item["local_path"])
                cache_key = str(path.resolve())
                cached_content = path_content_cache.get(cache_key)
                if cached_content is None:
                    content = path.read_bytes()
                    digest = hashlib.sha256(content).hexdigest()
                    path_content_cache[cache_key] = (content, digest)
                else:
                    content, digest = cached_content
                size_bytes = len(content)
                occurrence_count += 1
                occurrence_declared_bytes += size_bytes
                file_id = file_id_by_digest.get(digest)
                if file_id is None:
                    file_id = f"file_{len(files) + 1}"
                    file_id_by_digest[digest] = file_id
                    content_type = item.get("content_type") or "application/octet-stream"
                    encoded = base64.b64encode(content).decode("ascii")
                    files[file_id] = {
                        "__generation_file__": True,
                        "filename": item.get("filename") or path.name,
                        "content_type": content_type,
                        "size_bytes": size_bytes,
                        "encoding": "base64",
                        "data": "data:" + content_type + ";base64," + encoded,
                        "sha256": digest,
                        "node_id": item.get("node_id"),
                    }
                return {
                    "__generation_file_ref__": file_id,
                    "filename": item.get("filename") or path.name,
                    "content_type": item.get("content_type") or "application/octet-stream",
                    "size_bytes": size_bytes,
                    "node_id": item.get("node_id"),
                }
            if isinstance(item, dict):
                return {key: externalize(child) for key, child in item.items()}
            if isinstance(item, list):
                return [externalize(child) for child in item]
            return item

        externalized = externalize(value)
        unique_declared_bytes = sum(int(item.get("size_bytes") or 0) for item in files.values())
        unique_base64_characters = sum(
            len(str(item.get("data") or "").split(",", 1)[1])
            for item in files.values()
            if isinstance(item.get("data"), str) and "," in str(item.get("data"))
        )
        externalized["files"] = files
        return externalized, {
            "transport_generation_file_occurrences": occurrence_count,
            "transport_unique_file_count": len(files),
            "transport_duplicate_file_occurrences": max(0, occurrence_count - len(files)),
            "transport_occurrence_declared_file_bytes": occurrence_declared_bytes,
            "transport_unique_declared_file_bytes": unique_declared_bytes,
            "transport_unique_base64_character_count": unique_base64_characters,
            "transport_saved_declared_file_bytes": max(0, occurrence_declared_bytes - unique_declared_bytes),
        }

    def _externalize(self, value: Any) -> Any:
        """Legacy single-value externalizer retained for compatibility/tests."""
        if isinstance(value, dict) and value.get("__generation_file__"):
            path = Path(value["local_path"])
            content_type = value.get("content_type") or "application/octet-stream"
            return {"__generation_file__": True, "filename": value.get("filename") or path.name, "content_type": content_type, "size_bytes": path.stat().st_size, "encoding": "base64", "data": "data:" + content_type + ";base64," + base64.b64encode(path.read_bytes()).decode("ascii"), "node_id": value.get("node_id")}
        if isinstance(value, dict):
            return {k: self._externalize(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._externalize(v) for v in value]
        return value
