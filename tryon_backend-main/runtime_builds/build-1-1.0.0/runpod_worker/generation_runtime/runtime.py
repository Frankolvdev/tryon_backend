from __future__ import annotations

import base64
import copy
import io
import json
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


class GenerationRuntime:
    CONTRACT = "tryon.generation-runtime/v1"

    def __init__(self, *, comfy_url: str | None = None) -> None:
        self.comfy_url = (comfy_url or os.getenv("COMFYUI_URL") or "http://127.0.0.1:8188").rstrip("/")
        self.root = Path(os.getenv("GENERATION_RUNTIME_DIR") or tempfile.gettempdir()) / "tryon-runpod-runtime"
        self.root.mkdir(parents=True, exist_ok=True)

    def execute(self, payload: dict[str, Any], progress: Callable[[float, str], None] | None = None) -> dict[str, Any]:
        if payload.get("runtime_contract") != self.CONTRACT:
            raise ValueError("Unsupported Generation Runtime contract.")
        module = payload.get("module")
        context = self._materialize(copy.deepcopy(payload.get("context") or {}), self.root / str(payload.get("execution_id") or uuid4()))
        if not isinstance(module, dict):
            raise ValueError("Generation module payload is missing.")
        steps = [step for step in sorted(module.get("steps") or [], key=lambda row: row.get("position", 0)) if step.get("is_enabled")]
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
                else:
                    raise ValueError(f"Unsupported generation module step type: {step_type}")
                GenerationRuntimeContext.merge_step_outputs(context, key, outputs)
                duration_ms = int((time.monotonic()-started)*1000)
                metrics.add_step(step_key=key, step_type=step_type, duration_ms=duration_ms, status="completed")
                states.append({"step_key": key, "step_type": step_type, "status": "completed", "duration_ms": duration_ms, "outputs": self._externalize(outputs)})
                if progress:
                    progress(((index + 1) / max(len(steps), 1)) * 100, f"Step '{key}' completed.")
            except Exception as exc:
                duration_ms = int((time.monotonic()-started)*1000)
                metrics.add_step(step_key=key, step_type=str(step.get("step_type") or ""), duration_ms=duration_ms, status="failed")
                states.append({"step_key": key, "step_type": str(step.get("step_type") or ""), "status": "failed", "duration_ms": duration_ms, "outputs": {}, "error": str(exc)})
                return {"runtime_contract": self.CONTRACT, "status": "failed", "error": str(exc), "steps": states, "metrics": metrics.snapshot()}
        outputs = GenerationRuntimeContext.resolve_module_outputs(module.get("outputs") or [], context)
        return {"runtime_contract": self.CONTRACT, "status": "completed", "steps": states, "outputs": self._externalize(outputs), "context": self._externalize(context), "metrics": metrics.snapshot()}

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
            return {k: self._materialize(v, directory) for k,v in value.items()}
        if isinstance(value, list):
            return [self._materialize(v, directory) for v in value]
        return value

    def _workflow(self, step: dict[str, Any], context: dict[str, Any], execution_id: Any) -> dict[str, Any]:
        config = copy.deepcopy(step.get("configuration") or {})
        workflow = config.get("workflow")
        if not isinstance(workflow, dict):
            raise ValueError(f"Workflow step '{step.get('key')}' has no workflow JSON.")
        for binding in config.get("input_bindings") or []:
            source = binding.get("source_path") or binding.get("module_input_key")
            value = GenerationRuntimeContext.resolve(context, str(source or ""))
            node = workflow.get(str(binding.get("node_id")))
            if not isinstance(node, dict):
                raise ValueError(f"Workflow node '{binding.get('node_id')}' was not found.")
            if isinstance(value, dict) and value.get("__generation_file__"):
                value = self._upload_input(Path(value["local_path"]), str(execution_id))
            node.setdefault("inputs", {})[binding["input_field"]] = value
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
            response = client.post(f"{self.comfy_url}/upload/image", files={"image": (path.name, handle)}, data={"type":"input", "subfolder":f"generation-modules/{execution_id}", "overwrite":"true"})
            response.raise_for_status(); data=response.json()
        return "/".join(part for part in [data.get("subfolder"), data.get("name")] if part)

    def _execute_comfy(self, workflow: dict[str, Any], timeout: int) -> dict[str, Any]:
        client_id=uuid4().hex
        with httpx.Client(timeout=60) as client:
            response=client.post(f"{self.comfy_url}/prompt", json={"prompt":workflow,"client_id":client_id}); response.raise_for_status(); prompt_id=response.json()["prompt_id"]
        started=time.monotonic(); history=None
        while time.monotonic()-started < timeout:
            with httpx.Client(timeout=60) as client:
                data=client.get(f"{self.comfy_url}/history/{prompt_id}").raise_for_status().json()
            history=data.get(prompt_id)
            if history:
                break
            time.sleep(1)
        if not history:
            raise TimeoutError(f"ComfyUI workflow exceeded {timeout} seconds.")
        files=[]
        for node_id,node_output in (history.get("outputs") or {}).items():
            for category in ("images","gifs","videos","audio"):
                for item in node_output.get(category) or []:
                    params={"filename":item.get("filename"),"subfolder":item.get("subfolder") or "","type":item.get("type") or "output"}
                    with httpx.Client(timeout=300) as client:
                        content=client.get(f"{self.comfy_url}/view", params=params).raise_for_status().content
                    suffix=Path(str(item.get("filename") or ".bin")).suffix or ".bin"
                    target=self.root/f"{uuid4().hex}{suffix}"; target.write_bytes(content)
                    files.append({"__generation_file__":True,"local_path":str(target),"filename":item.get("filename") or target.name,"content_type":item.get("content_type"),"size_bytes":len(content),"node_id":str(node_id)})
        return {"prompt_id":prompt_id,"files":files}

    def _python(self, step: dict[str, Any], context: dict[str, Any], execution_id: Any) -> dict[str, Any]:
        config=step.get("configuration") or {}; source=config.get("source_code") or ""; entrypoint=config.get("entrypoint") or "run"; timeout=int(config.get("timeout_seconds") or 300)
        inputs=GenerationRuntimeContext.step_inputs(context, step.get("input_mapping"))
        inputs=self._to_images(inputs)
        allowed={"PIL","math","json","io","base64"}; real_import=__import__
        def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name.split('.',1)[0] not in allowed: raise ImportError(f"Import '{name}' is not allowed in Python nodes.")
            return real_import(name,globals,locals,fromlist,level)
        builtins={"len":len,"min":min,"max":max,"sum":sum,"sorted":sorted,"range":range,"enumerate":enumerate,"zip":zip,"str":str,"int":int,"float":float,"bool":bool,"dict":dict,"list":list,"tuple":tuple,"set":set,"abs":abs,"round":round,"any":any,"all":all,"isinstance":isinstance,"Exception":Exception,"ValueError":ValueError,"TypeError":TypeError,"ImportError":ImportError,"__import__":safe_import}
        ns={"__builtins__":builtins,"json":json}; exec(compile(source,f"generation_module_{step.get('key')}.py","exec"),ns,ns); fn=ns.get(entrypoint)
        if not callable(fn): raise ValueError(f"Python entrypoint '{entrypoint}' was not found.")
        with ThreadPoolExecutor(max_workers=1) as executor:
            future=executor.submit(fn,inputs)
            try: result=future.result(timeout=timeout)
            except FutureTimeoutError as exc: raise TimeoutError(f"Python step '{step.get('key')}' exceeded {timeout} seconds.") from exc
        result={} if result is None else (result if isinstance(result,dict) else {"result":result})
        return self._save_images(result, self.root/str(execution_id), str(step.get("key")))

    def _to_images(self,value:Any)->Any:
        if isinstance(value,dict) and value.get("__generation_file__") and str(value.get("content_type") or "").startswith("image/"):
            image=Image.open(value["local_path"]); image.load(); return image
        if isinstance(value,dict): return {k:self._to_images(v) for k,v in value.items()}
        if isinstance(value,list): return [self._to_images(v) for v in value]
        return value

    def _save_images(self,value:Any,directory:Path,prefix:str)->Any:
        if isinstance(value,Image.Image):
            directory.mkdir(parents=True,exist_ok=True); target=directory/f"{prefix}-{uuid4().hex[:10]}.png"; image=value if value.mode in {"RGB","RGBA","L"} else value.convert("RGBA"); image.save(target,"PNG")
            return {"__generation_file__":True,"local_path":str(target),"filename":target.name,"content_type":"image/png","size_bytes":target.stat().st_size}
        if isinstance(value,dict): return {k:self._save_images(v,directory,prefix) for k,v in value.items()}
        if isinstance(value,list): return [self._save_images(v,directory,prefix) for v in value]
        return value

    def _externalize(self,value:Any)->Any:
        if isinstance(value,dict) and value.get("__generation_file__"):
            path=Path(value["local_path"]); content_type=value.get("content_type") or "application/octet-stream"
            return {"__generation_file__":True,"filename":value.get("filename") or path.name,"content_type":content_type,"size_bytes":path.stat().st_size,"encoding":"base64","data":"data:"+content_type+";base64,"+base64.b64encode(path.read_bytes()).decode("ascii"),"node_id":value.get("node_id")}
        if isinstance(value,dict): return {k:self._externalize(v) for k,v in value.items()}
        if isinstance(value,list): return [self._externalize(v) for v in value]
        return value
