import asyncio
import json
import os
import shlex
import signal
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import modal

APP_NAME = "ia-comfyui-python-build"
VOLUME_NAME = "ia-comfyui-python-volume-modal"
VOLUME_PATH = "/models"
COMFYUI_PORT = 8188
STARTUP_TIMEOUT = int(os.getenv("TRYON_MODAL_STARTUP_TIMEOUT", "600"))

MODAL_GPU_ALIASES = {"A10G": "A10"}
MODAL_GPU_ALLOWED = {
    "T4", "L4", "A10", "L40S", "A100", "A100-40GB", "A100-80GB",
    "RTX-PRO-6000", "H100", "H100!", "H200", "B200", "B200+", "B300",
}


def _resolve_modal_gpu(value: str) -> str:
    requested = str(value or "L40S").strip()
    normalized = MODAL_GPU_ALIASES.get(requested.upper(), requested.upper())
    if normalized not in MODAL_GPU_ALLOWED:
        allowed = ", ".join(sorted(MODAL_GPU_ALLOWED))
        raise ValueError(
            f"GPU de Modal no válida: {requested!r}. Valores permitidos: {allowed}"
        )
    return normalized


GPU = _resolve_modal_gpu(os.getenv("TRYON_MODAL_GPU", "L40S"))
MIN_CONTAINERS = int(os.getenv("TRYON_MODAL_MIN_CONTAINERS", "0"))
MAX_CONTAINERS = int(os.getenv("TRYON_MODAL_MAX_CONTAINERS", "3"))
GENERATION_CONCURRENCY = int(os.getenv("TRYON_MODAL_CONCURRENCY", "1"))
INPUT_CONCURRENCY = int(os.getenv("TRYON_MODAL_INPUT_CONCURRENCY", "1000"))
SCALEDOWN_WINDOW = int(os.getenv("TRYON_MODAL_SCALEDOWN_WINDOW", "300"))
CPU_MEMORY_REQUEST_MB = int(os.getenv("TRYON_MODAL_CPU_MEMORY_REQUEST_MB", "32768"))
EXECUTION_TIMEOUT = int(os.getenv("TRYON_MODAL_EXECUTION_TIMEOUT", "1800"))

COMFYUI_ROOT = Path("/app/ComfyUI")
COMFYUI_MAIN = COMFYUI_ROOT / "main.py"
RUNTIME_ROOT = Path("/app/runtime")
MODELS_ROOT = Path(os.getenv("MODELS_ROOT", VOLUME_PATH))
COMFY_USER_ROOT = Path(os.getenv("COMFY_USER_ROOT", "/tmp/comfyui-user"))
COMFY_DATABASE_URL = os.getenv(
    "COMFY_DATABASE_URL",
    f"sqlite:///{COMFY_USER_ROOT / 'comfyui.db'}",
)

app = modal.App(APP_NAME)
models_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
image = modal.Image.from_dockerfile("Dockerfile.modal").pip_install("fastapi")


def _modal_trace(event: str, *, role: str, **fields) -> None:
    payload = {
        "event": event,
        "role": role,
        "task_id": os.getenv("MODAL_TASK_ID"),
        "container_id": os.getenv("MODAL_CONTAINER_ID"),
        "function_call_id": os.getenv("MODAL_FUNCTION_CALL_ID"),
        "function_id": os.getenv("MODAL_FUNCTION_ID"),
        "region": os.getenv("MODAL_REGION"),
        "image_id": os.getenv("MODAL_IMAGE_ID"),
        "timestamp": time.time(),
        **fields,
    }
    print("[tryon-modal-trace] " + json.dumps(payload, ensure_ascii=False, default=str), flush=True)


MODEL_DIAGNOSTICS_ENABLED = os.getenv("TRYON_MODAL_MODEL_DIAGNOSTICS", "true").strip().lower() in {"1", "true", "yes", "on"}
_MODEL_INPUT_HINTS = (
    "ckpt_name", "checkpoint", "model_name", "model_source", "unet_name",
    "vae_name", "clip_name", "control_net_name", "controlnet_name",
    "lora_name", "lora", "ipadapter_file", "pulid_file",
)


def _diagnostic_gpu_state() -> dict:
    state = {}
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if completed.returncode == 0:
            rows = []
            for line in completed.stdout.splitlines():
                values = [value.strip() for value in line.split(",")]
                if len(values) == 6:
                    rows.append({
                        "index": values[0],
                        "name": values[1],
                        "memory_total_mb": values[2],
                        "memory_used_mb": values[3],
                        "memory_free_mb": values[4],
                        "utilization_percent": values[5],
                    })
            state["gpus"] = rows
        elif completed.stderr.strip():
            state["error"] = completed.stderr.strip()[-500:]
    except Exception as exc:
        state["error"] = f"{exc.__class__.__name__}: {exc}"
    return state


def _looks_like_workflow(value) -> bool:
    if not isinstance(value, dict) or not value:
        return False
    checked = 0
    matches = 0
    for node in value.values():
        if not isinstance(node, dict):
            continue
        checked += 1
        if isinstance(node.get("class_type"), str) and isinstance(node.get("inputs"), dict):
            matches += 1
        if checked >= 12:
            break
    return matches > 0 and matches == checked


def _decode_diagnostic_workflow(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return None
        return decoded if isinstance(decoded, dict) else None
    return None


def _find_payload_workflows(payload) -> list[dict]:
    workflows = []
    seen_ids = set()

    def visit(value, path: str) -> None:
        if isinstance(value, dict):
            if _looks_like_workflow(value):
                marker = id(value)
                if marker not in seen_ids:
                    seen_ids.add(marker)
                    workflows.append({"path": path, "workflow": value})
                return
            for key, child in value.items():
                if str(key).lower() == "workflow":
                    decoded = _decode_diagnostic_workflow(child)
                    if _looks_like_workflow(decoded):
                        marker = id(decoded)
                        if marker not in seen_ids:
                            seen_ids.add(marker)
                            workflows.append({"path": f"{path}.{key}", "workflow": decoded})
                        continue
                visit(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    visit(payload, "payload")
    return workflows


def _workflow_model_inventory(workflow: dict) -> dict:
    loaders = []
    purge_nodes = []
    for raw_node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        node_id = str(raw_node_id)
        class_type = str(node.get("class_type") or "")
        inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
        class_lower = class_type.lower()

        model_inputs = {}
        for key, value in inputs.items():
            key_lower = str(key).lower()
            if any(hint in key_lower for hint in _MODEL_INPUT_HINTS):
                if isinstance(value, (str, int, float, bool)) or value is None:
                    model_inputs[str(key)] = value

        loader_like = bool(model_inputs) or any(
            token in class_lower
            for token in ("loader", "checkpoint", "controlnet", "ipadapter", "sam3")
        )
        if loader_like:
            loaders.append({
                "node_id": node_id,
                "class_type": class_type,
                "model_inputs": model_inputs,
            })

        if "purge" in class_lower or "unload" in class_lower or "empty cache" in class_lower:
            purge_nodes.append({
                "node_id": node_id,
                "class_type": class_type,
                "purge_cache": inputs.get("purge_cache"),
                "purge_models": inputs.get("purge_models"),
            })

    return {
        "node_count": len(workflow),
        "loader_count": len(loaders),
        "purge_count": len(purge_nodes),
        "loaders": loaders,
        "purge_nodes": purge_nodes,
    }


def _emit_model_diagnostics(payload, *, phase: str, execution_id: str) -> None:
    if not MODEL_DIAGNOSTICS_ENABLED:
        return
    try:
        workflows = _find_payload_workflows(payload)
        inventories = []
        for item in workflows:
            inventories.append({
                "path": item["path"],
                **_workflow_model_inventory(item["workflow"]),
            })
        _modal_trace(
            "model_diagnostics",
            role="pipeline_server",
            phase=phase,
            execution_id=execution_id,
            workflow_count=len(inventories),
            workflows=inventories,
            gpu=_diagnostic_gpu_state(),
        )
    except Exception as exc:
        _modal_trace(
            "model_diagnostics_error",
            role="pipeline_server",
            phase=phase,
            execution_id=execution_id,
            error_type=exc.__class__.__name__,
            error=str(exc),
        )


def _port_is_ready() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", COMFYUI_PORT), timeout=1):
            return True
    except OSError:
        return False


def _wait_until_ready(process: subprocess.Popen, timeout: int = STARTUP_TIMEOUT) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_is_ready():
            print(f"[modal] ComfyUI listo en el puerto {COMFYUI_PORT}.", flush=True)
            return
        return_code = process.poll()
        if return_code is not None:
            raise RuntimeError(
                f"ComfyUI terminó antes de abrir el puerto {COMFYUI_PORT} "
                f"(código {return_code})."
            )
        time.sleep(1)
    raise TimeoutError(
        f"ComfyUI no abrió el puerto {COMFYUI_PORT} en {timeout} segundos."
    )


def _ensure_linux_machine_id() -> None:
    """Provide the machine-id expected by ComfyUI-Execute-Python on Modal."""
    primary = Path("/etc/machine-id")
    dbus = Path("/var/lib/dbus/machine-id")

    machine_id = ""
    if primary.is_file():
        try:
            candidate = primary.read_text(encoding="utf-8").strip().lower()
            if len(candidate) == 32 and all(char in "0123456789abcdef" for char in candidate):
                machine_id = candidate
        except OSError:
            pass
    if not machine_id:
        machine_id = uuid.uuid4().hex

    primary.parent.mkdir(parents=True, exist_ok=True)
    primary.write_text(machine_id + "\n", encoding="utf-8")
    dbus.parent.mkdir(parents=True, exist_ok=True)
    dbus.write_text(machine_id + "\n", encoding="utf-8")
    print(f"[runtime] Linux machine-id preparado para Execute Python: {machine_id[:8]}…", flush=True)


def _ensure_sam3_volume_link() -> None:
    """Expose the external SAM3 tree where TBG-SAM3 scans it directly."""
    source = MODELS_ROOT / "sam3"
    target = COMFYUI_ROOT / "models" / "sam3"

    if not source.is_dir():
        print(f"[runtime] SAM3 no enlazado: no existe el directorio {source}.", flush=True)
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        try:
            if target.resolve() == source.resolve():
                print(f"[runtime] SAM3 ya enlazado: {target} -> {source}", flush=True)
                return
        except OSError:
            pass
        target.unlink()
    elif target.exists():
        if target.is_dir() and not any(target.iterdir()):
            target.rmdir()
        else:
            raise RuntimeError(
                f"No se puede crear el enlace SAM3 porque {target} ya existe "
                "y contiene datos. No se eliminó ni sobrescribió nada."
            )

    target.symlink_to(source, target_is_directory=True)
    if not target.is_dir():
        raise RuntimeError(f"No se pudo crear el enlace SAM3: {target} -> {source}")
    print(f"[runtime] SAM3 enlazado desde el Volume: {target} -> {source}", flush=True)
    checkpoint = source / "sam3.pt"
    if not checkpoint.is_file():
        print(f"[runtime] Advertencia: no se encontró {checkpoint}.", flush=True)


def _prepare_runtime_directories() -> None:
    (COMFYUI_ROOT / "models").mkdir(parents=True, exist_ok=True)
    (COMFY_USER_ROOT / "default" / "workflows").mkdir(parents=True, exist_ok=True)
    _ensure_linux_machine_id()
    _ensure_sam3_volume_link()
    print(f"[runtime] Modelos externos registrados desde: {MODELS_ROOT}", flush=True)
    print(f"[runtime] Directorio temporal de usuario: {COMFY_USER_ROOT}", flush=True)


def _run_performance_probe(env: dict[str, str]) -> None:
    probe = RUNTIME_ROOT / "scripts" / "performance_probe.py"
    if not probe.is_file():
        return
    try:
        subprocess.run([sys.executable, str(probe)], env=env, check=False)
    except OSError as exc:
        print(f"[modal] No se pudo ejecutar performance_probe.py: {exc}", flush=True)


def _proxy_app():
    from aiohttp import ClientSession, WSMsgType
    from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
    from fastapi.responses import Response

    web_app = FastAPI()
    upstream_http = f"http://127.0.0.1:{COMFYUI_PORT}"
    upstream_ws = f"ws://127.0.0.1:{COMFYUI_PORT}"
    hop_headers = {
        "connection", "keep-alive", "proxy-authenticate",
        "proxy-authorization", "te", "trailers",
        "transfer-encoding", "upgrade", "content-length",
    }

    def clean_headers(headers):
        return {k: v for k, v in headers.items() if k.lower() not in hop_headers and k.lower() != "host"}

    def upstream_request_headers(headers):
        forwarded = clean_headers(headers)
        if any(key.lower() == "origin" for key in forwarded):
            forwarded["Origin"] = upstream_http
        if any(key.lower() == "referer" for key in forwarded):
            forwarded["Referer"] = f"{upstream_http}/"
        return forwarded

    @web_app.post("/api/tryon/pipeline")
    async def execute_tryon_pipeline(request: Request):
        """Execute one complete workflow/Python pipeline in this GPU container."""
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON payload.") from exc

        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=400,
                detail="Pipeline payload must be a JSON object.",
            )

        if payload.get("runtime_contract") != "tryon.generation-runtime/v1":
            raise HTTPException(
                status_code=400,
                detail="Unsupported Generation Runtime contract.",
            )

        runtime_worker = RUNTIME_ROOT / "runpod_worker"
        if str(runtime_worker) not in sys.path:
            sys.path.insert(0, str(runtime_worker))

        try:
            from generation_runtime import GenerationRuntime

            runtime = GenerationRuntime(comfy_url=upstream_http)
            result = await asyncio.to_thread(runtime.execute, payload)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        return result

    @web_app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
    async def proxy_http(path: str, request: Request):
        _modal_trace(
            "proxy_http_request",
            role="web_proxy",
            method=request.method,
            path=f"/{path}",
            query=str(request.url.query or ""),
            user_agent=request.headers.get("user-agent"),
            origin=request.headers.get("origin"),
            referer=request.headers.get("referer"),
            forwarded_for=request.headers.get("x-forwarded-for"),
        )
        target = f"{upstream_http}/{path}"
        if request.url.query:
            target += f"?{request.url.query}"
        body = await request.body()
        async with ClientSession() as session:
            async with session.request(
                request.method,
                target,
                headers=upstream_request_headers(request.headers),
                data=body or None,
                allow_redirects=False,
            ) as upstream:
                content = await upstream.read()
                return Response(
                    content=content,
                    status_code=upstream.status,
                    headers=clean_headers(upstream.headers),
                    media_type=upstream.content_type if upstream.content_type else None,
                )

    @web_app.websocket("/{path:path}")
    async def proxy_websocket(websocket: WebSocket, path: str):
        headers = websocket.headers
        _modal_trace(
            "proxy_websocket_connect",
            role="web_proxy",
            path=f"/{path}",
            user_agent=headers.get("user-agent"),
            origin=headers.get("origin"),
            forwarded_for=headers.get("x-forwarded-for"),
        )
        target = f"{upstream_ws}/{path}"
        query = websocket.scope.get("query_string", b"").decode("latin-1")
        if query:
            target += f"?{query}"
        websocket_handshake_headers = hop_headers | {
            "host", "sec-websocket-key", "sec-websocket-version",
            "sec-websocket-extensions", "sec-websocket-protocol",
        }
        forwarded = {
            key.decode("latin-1"): value.decode("latin-1")
            for key, value in websocket.scope.get("headers", [])
            if key.decode("latin-1").lower() not in websocket_handshake_headers
        }
        forwarded["Origin"] = upstream_http
        async with ClientSession() as session:
            async with session.ws_connect(target, headers=forwarded, autoping=True) as upstream:
                await websocket.accept()

                async def client_to_upstream():
                    try:
                        while True:
                            message = await websocket.receive()
                            kind = message.get("type")
                            if kind == "websocket.disconnect":
                                break
                            if message.get("text") is not None:
                                await upstream.send_str(message["text"])
                            elif message.get("bytes") is not None:
                                await upstream.send_bytes(message["bytes"])
                    except WebSocketDisconnect:
                        pass
                    finally:
                        await upstream.close()

                async def upstream_to_client():
                    async for message in upstream:
                        if message.type == WSMsgType.TEXT:
                            await websocket.send_text(message.data)
                        elif message.type == WSMsgType.BINARY:
                            await websocket.send_bytes(message.data)
                        elif message.type in {WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR}:
                            break

                tasks = [
                    asyncio.create_task(client_to_upstream()),
                    asyncio.create_task(upstream_to_client()),
                ]
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for task in done:
                    task.result()
                _modal_trace(
                    "proxy_websocket_disconnect",
                    role="web_proxy",
                    path=f"/{path}",
                )

    return web_app


@app.cls(
    image=image,
    gpu=GPU,
    min_containers=MIN_CONTAINERS,
    max_containers=MAX_CONTAINERS,
    volumes={VOLUME_PATH: models_volume},
    timeout=EXECUTION_TIMEOUT,
    scaledown_window=SCALEDOWN_WINDOW,
    memory=CPU_MEMORY_REQUEST_MB,
    enable_memory_snapshot=True,
    experimental_options={"enable_gpu_snapshot": True},
)
@modal.concurrent(max_inputs=GENERATION_CONCURRENCY)
class ComfyUIServer:
    def _start_process(self) -> None:
        if not COMFYUI_MAIN.is_file():
            raise RuntimeError(f"No se encontró ComfyUI en {COMFYUI_MAIN}.")

        env = os.environ.copy()
        env["RUNTIME_PROVIDER"] = "modal"
        env["COMFYUI_PORT"] = str(COMFYUI_PORT)
        env["MODELS_ROOT"] = str(MODELS_ROOT)
        env["COMFY_USER_ROOT"] = str(COMFY_USER_ROOT)
        env["COMFY_DATABASE_URL"] = COMFY_DATABASE_URL

        _prepare_runtime_directories()
        _run_performance_probe(env)

        extra_args = shlex.split(env.get("COMFYUI_EXTRA_ARGS", ""))
        command = [
            sys.executable,
            str(COMFYUI_MAIN),
            "--listen",
            "127.0.0.1",
            "--port",
            str(COMFYUI_PORT),
            "--user-directory",
            str(COMFY_USER_ROOT),
            "--database-url",
            COMFY_DATABASE_URL,
            *extra_args,
        ]
        print(f"[modal] Iniciando ComfyUI directamente: {shlex.join(command)}", flush=True)
        self.comfyui_process = subprocess.Popen(
            command,
            cwd=str(COMFYUI_ROOT),
            env=env,
            start_new_session=True,
        )
        _wait_until_ready(self.comfyui_process)

    @modal.enter(snap=True)
    def initialize_for_snapshot(self) -> None:
        # Basic Modal memory snapshot: prepare only safe runtime state. Do not
        # preload models or initialize CUDA in this phase.
        _modal_trace(
            "container_snapshot_initialize",
            role="pipeline_server",
            snapshot_mode="basic_memory_snapshot",
            comfyui_started=False,
            models_loaded=False,
        )
        os.environ["RUNTIME_PROVIDER"] = "modal"
        os.environ["COMFYUI_PORT"] = str(COMFYUI_PORT)
        os.environ["MODELS_ROOT"] = str(MODELS_ROOT)
        os.environ["COMFY_USER_ROOT"] = str(COMFY_USER_ROOT)
        os.environ["COMFY_DATABASE_URL"] = COMFY_DATABASE_URL

        prepared = []
        skipped = []
        try:
            _prepare_runtime_directories()
            prepared.append("runtime_directories")
        except Exception as exc:
            skipped.append(f"runtime_directories:{type(exc).__name__}")
            _modal_trace(
                "snapshot_optional_prepare_error",
                role="pipeline_server",
                step="runtime_directories",
                error_type=type(exc).__name__,
                error=str(exc),
            )

        try:
            runtime_worker = RUNTIME_ROOT / "runpod_worker"
            if str(runtime_worker) not in sys.path:
                sys.path.insert(0, str(runtime_worker))
            from generation_runtime import GenerationRuntime  # noqa: F401
            prepared.append("generation_runtime_imports")
        except Exception as exc:
            skipped.append(f"generation_runtime_imports:{type(exc).__name__}")
            _modal_trace(
                "snapshot_optional_prepare_error",
                role="pipeline_server",
                step="generation_runtime_imports",
                error_type=type(exc).__name__,
                error=str(exc),
            )

        self.comfyui_process = None
        _modal_trace(
            "container_snapshot_ready",
            role="pipeline_server",
            snapshot_mode="basic_memory_snapshot",
            prepared=prepared,
            skipped=skipped,
            comfyui_started=False,
            models_loaded=False,
        )
        print(
            "[modal] Snapshot básico preparado sin precarga de modelos ni CUDA.",
            flush=True,
        )

    @modal.enter(snap=False)
    def restore_after_snapshot(self) -> None:
        # Restore follows the original normal GPU startup path and does not
        # depend on a subprocess surviving the snapshot.
        _modal_trace(
            "container_restore_start",
            role="pipeline_server",
            startup_mode="normal_gpu_after_basic_snapshot",
        )
        self.comfyui_process = None
        self._start_process()
        print("[modal] ComfyUI iniciado normalmente después del snapshot básico.", flush=True)
        _modal_trace(
            "container_ready",
            role="pipeline_server",
            restored_from_snapshot=True,
            comfyui_snapshotted=False,
            models_snapshotted=False,
            startup_mode="normal_gpu_after_basic_snapshot",
        )

    @modal.method()
    def run_pipeline(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Pipeline payload must be a JSON object.")
        if payload.get("runtime_contract") != TRYON_RUNTIME_CONTRACT:
            raise ValueError("Unsupported Generation Runtime contract.")
        execution_id = str(payload.get("execution_id") or "")
        _emit_model_diagnostics(payload, phase="before_pipeline", execution_id=execution_id)
        _modal_trace("pipeline_start", role="pipeline_server", execution_id=execution_id)
        runtime_worker = RUNTIME_ROOT / "runpod_worker"
        if str(runtime_worker) not in sys.path:
            sys.path.insert(0, str(runtime_worker))
        from generation_runtime import GenerationRuntime
        runtime = GenerationRuntime(comfy_url=f"http://127.0.0.1:{COMFYUI_PORT}")
        started = time.monotonic()
        try:
            result = runtime.execute(payload)
        except BaseException as exc:
            _modal_trace(
                "pipeline_error",
                role="pipeline_server",
                execution_id=execution_id,
                error_type=exc.__class__.__name__,
                error=str(exc),
            )
            raise
        _modal_trace(
            "pipeline_end",
            role="pipeline_server",
            execution_id=execution_id,
            duration_ms=int((time.monotonic() - started) * 1000),
            status=result.get("status") if isinstance(result, dict) else None,
        )
        _emit_model_diagnostics(payload, phase="after_pipeline", execution_id=execution_id)
        return result

    @modal.asgi_app(requires_proxy_auth=True)
    def comfyui(self):
        return _proxy_app()

    @modal.exit()
    def shutdown(self) -> None:
        _modal_trace("container_exit", role="pipeline_server")
        process = getattr(self, "comfyui_process", None)
        if process is None or process.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            process.wait(timeout=15)
        except ProcessLookupError:
            return
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
