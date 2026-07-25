import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from app.models.runtime_builder_config import RuntimeBuilderConfig


@dataclass
class ValidationIssue:
    level: str
    field: str
    message: str


class RuntimeBuilderService:
    """Validate and generate reproducible ComfyUI runtimes.

    This keeps the existing workflow/custom-node/model discovery flow intact.  The
    only dependency change is a conservative renderer that preserves PEP 508
    extras and markers instead of blindly inserting ``==``.
    """

    DEFAULT_MODAL_VOLUME_PATH = "/models"


    PROTECTED_GPU_PACKAGES = {
        "torch", "torchvision", "torchaudio", "xformers", "triton",
        "onnxruntime-gpu", "flash-attn",
    }

    # Single source of truth used by the API endpoint, validation and exports.
    # MEGA31 accidentally removed this class attribute while the endpoint still
    # referenced it, causing GET /runtime-builder/config to fail at runtime.
    RECOMMENDED_PROFILE = {
        "id": "universal-modal-rtx5090",
        "label": "Universal GPU — Modal + RTX 5090",
        "python_version": "3.11",
        "cuda_version": "12.8.1",
        "pytorch_index_url": "https://download.pytorch.org/whl/cu128",
        "comfyui_version": "0.15.1",
        "comfyui_frontend_version": "1.39.19",
        "comfyui_commit": "3dd10a59c00248d00f0cb0ab794ff1bb9fb00a5f",
    }

    # Nombres alternativos de carpetas locales. El exportador siempre copia la
    # instalación local y nunca descarga ni reemplaza Custom Nodes desde Git.
    CUSTOM_NODE_ALIASES = {
        "comfyui-execute-python": ("execute-python",),
        "was-node-suite-comfyui": ("was-ns",),
        "comfyliterals": ("comfy-literals", "comfyui-comfyliterals"),
    }

    REQUIRED_CUSTOM_NODES = (
        {"name": "ComfyUI-Manager", "repository": "https://github.com/Comfy-Org/ComfyUI-Manager.git", "commit": None, "enabled": True, "install_requirements": True, "required_by_default": True},
        {"name": "rgthree-comfy", "repository": "https://github.com/rgthree/rgthree-comfy.git", "commit": None, "enabled": True, "install_requirements": True, "required_by_default": True},
        {"name": "ComfyUI-Easy-Use", "repository": "https://github.com/yolain/ComfyUI-Easy-Use.git", "commit": None, "enabled": True, "install_requirements": True, "required_by_default": True},
        {"name": "ComfyUI-Lora-Manager", "repository": "https://github.com/willmiao/ComfyUI-Lora-Manager.git", "commit": None, "enabled": True, "install_requirements": True, "required_by_default": True},
        {"name": "ComfyUI-KJNodes", "repository": "https://github.com/kijai/ComfyUI-KJNodes.git", "commit": None, "enabled": True, "install_requirements": True, "required_by_default": True},
        {"name": "ComfyUI_essentials", "repository": "https://github.com/cubiq/ComfyUI_essentials.git", "commit": None, "enabled": True, "install_requirements": True, "required_by_default": True},
        {"name": "was-node-suite-comfyui", "repository": "https://github.com/WASasquatch/was-node-suite-comfyui.git", "commit": None, "enabled": True, "install_requirements": True, "required_by_default": True},
        {"name": "ComfyUI-Logic", "repository": "https://github.com/theUpsider/ComfyUI-Logic.git", "commit": None, "enabled": True, "install_requirements": True, "required_by_default": True},
        {"name": "ComfyUI-Execute-Python", "repository": "https://github.com/mozhaa/ComfyUI-Execute-Python.git", "commit": None, "enabled": True, "install_requirements": True, "required_by_default": True},
        {"name": "ComfyLiterals", "repository": "https://github.com/M1kep/ComfyLiterals.git", "commit": None, "enabled": True, "install_requirements": True, "required_by_default": True},
        {"name": "Anomalous_Model_Browser", "repository": "https://github.com/DemonGatanjieu/Anomalous_Model_Browser.git", "commit": None, "enabled": True, "install_requirements": True, "required_by_default": True},
    )

    @staticmethod
    def sanitize_runtime_name(value: str | None) -> str:
        import unicodedata
        normalized = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
        normalized = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
        normalized = re.sub(r"-+", "-", normalized)[:120].rstrip("-")
        if not normalized:
            normalized = "generation-runtime"
        if not normalized[0].isalpha():
            normalized = f"runtime-{normalized}"
        return normalized

    @staticmethod
    def merge_required_custom_nodes(nodes: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = [dict(item) for item in RuntimeBuilderService.REQUIRED_CUSTOM_NODES]
        keys = {str(item["repository"]).lower().removesuffix(".git") for item in merged}
        for item in nodes or []:
            repo = str(item.get("repository") or "").lower().removesuffix(".git")
            name = str(item.get("name") or "").lower()
            if repo in keys or any(str(x.get("name") or "").lower() == name for x in merged):
                continue
            merged.append(dict(item))
            if repo:
                keys.add(repo)
        return merged

    DEVELOPMENT_DEPENDENCIES = {
        "black", "flake8", "pytest", "pytest-cov", "pytest-asyncio",
        "coverage", "ruff", "isort", "mypy", "pre-commit", "tox",
        "nox", "bandit", "pylint", "autopep8", "yapf",
    }

    @staticmethod
    def _requirement_name(requirement: str) -> str:
        value = str(requirement or "").strip()
        value = value.split(";", 1)[0].strip()
        return re.split(r"\[|===|==|~=|!=|<=|>=|<|>|\s", value, maxsplit=1)[0].strip().lower()

    @staticmethod
    def is_runtime_dependency(requirement: str) -> bool:
        name = RuntimeBuilderService._requirement_name(requirement)
        return name not in RuntimeBuilderService.DEVELOPMENT_DEPENDENCIES and name not in RuntimeBuilderService.PROTECTED_GPU_PACKAGES

    @staticmethod
    def normalize_cuda_version(value: str | None) -> str:
        version = str(value or "").strip()
        if re.fullmatch(r"\d+\.\d+", version):
            return f"{version}.0"
        if re.fullmatch(r"\d+\.\d+\.\d+", version):
            return version
        raise ValueError(
            "La versión CUDA debe usar el formato mayor.menor o mayor.menor.parche, "
            "por ejemplo 12.8 o 12.8.0."
        )

    @staticmethod
    def _dependency_source(dependency: dict[str, Any]) -> str:
        return str(
            dependency.get("requirement")
            or dependency.get("package")
            or dependency.get("name")
            or ""
        ).strip()

    @staticmethod
    def render_requirement(dependency: dict[str, Any]) -> str:
        """Render one dependency as a valid PEP 508 requirement.

        Existing scanner output is accepted in either of these forms:
        - package=qrcode, version=[pil]       -> qrcode[pil]
        - package=onnxruntime-gpu, version="; marker" -> package; marker
        - package already containing extras/markers/specifier -> preserved
        - ordinary package + version -> package==version
        """

        raw_package = RuntimeBuilderService._dependency_source(dependency)
        raw_version = str(dependency.get("version") or "").strip()
        if not raw_package:
            raise ValueError("La dependencia no contiene package, name o requirement.")

        # mediapipe 0.10.0 no publica una distribución instalable para el
        # entorno Linux/Python usado por el runtime. 0.10.21 conserva la API
        # clásica utilizada por los Custom Nodes y sí dispone de wheels.
        package_name = raw_package.strip().lower()
        if package_name == "mediapipe" and raw_version in {"0.10.0", "==0.10.0"}:
            raw_version = "0.10.21"
        # PyAV 9.0.0 no ofrece wheel compatible con el runtime Linux/Python 3.10
        # y obliga a compilar contra FFmpeg, donde falla con toolchains actuales.
        # 12.3.0 mantiene la API usada por los nodos y dispone de wheels manylinux.
        if package_name == "av":
            version_number = raw_version.removeprefix("==").strip()
            if re.fullmatch(r"(?:8|9|10|11)(?:\.\d+){0,2}", version_number):
                raw_version = "12.3.0"

        # Some imported requirements already contain the whole PEP 508 string.
        if dependency.get("requirement"):
            candidate = raw_package
        elif raw_version.startswith("[") and raw_version.endswith("]"):
            # Fixes qrcode==[pil] generated by the previous renderer.
            candidate = f"{raw_package}{raw_version}"
        elif raw_version.startswith(";"):
            # Fixes onnxruntime-gpu==; marker.
            candidate = f"{raw_package}{raw_version}"
        elif not raw_version:
            candidate = raw_package
        elif re.match(r"^(===|==|~=|!=|<=|>=|<|>)", raw_version):
            candidate = f"{raw_package}{raw_version}"
        else:
            candidate = f"{raw_package}=={raw_version}"

        # Validación conservadora sin dependencias externas. El Runtime Builder
        # solo necesita impedir las formas que él mismo podía generar mal.
        if not candidate or candidate.startswith(("==", ";", "[")):
            raise ValueError(f"Dependencia Python inválida: {candidate!r}.")
        if "==[" in candidate or "==;" in candidate:
            raise ValueError(f"Dependencia Python inválida: {candidate!r}.")
        if any(char in candidate for char in ("\n", "\r", "\x00")):
            raise ValueError(f"Dependencia Python inválida: {candidate!r}.")
        return candidate

    @staticmethod
    def render_requirements(dependencies: list[dict[str, Any]]) -> list[str]:
        rendered: list[str] = []
        seen: set[str] = set()
        for dependency in dependencies:
            requirement = RuntimeBuilderService.render_requirement(dependency)
            if not RuntimeBuilderService.is_runtime_dependency(requirement):
                continue
            key = requirement.lower()
            if key not in seen:
                seen.add(key)
                rendered.append(requirement)
        return rendered

    @staticmethod
    def _is_modal(config: RuntimeBuilderConfig) -> bool:
        # Compatibilidad con configuraciones anteriores: todavía no existe un
        # selector visual de proveedor. Modal se detecta por plataforma/notas,
        # variables de entorno o por la existencia del Volume de modelos.
        values = [
            str(getattr(config, "target_platform", "") or ""),
            str(getattr(config, "notes", "") or ""),
        ]
        for item in getattr(config, "environment_variables", None) or []:
            values.extend([str(item.get("key") or ""), str(item.get("value") or "")])
        for volume in getattr(config, "volumes", None) or []:
            values.extend([
                str(volume.get("name") or ""),
                str(volume.get("mount_path") or volume.get("container_path") or volume.get("path") or ""),
            ])
        if any("modal" in value.lower() for value in values):
            return True

        # En el Runtime Builder actual, un Volume configurado junto con modelos
        # de estrategia volume representa el almacenamiento externo de Modal.
        # Esto evita depender de un campo de proveedor que aún no existe en UI.
        return bool(getattr(config, "volumes", None)) and RuntimeBuilderService._models_are_external(config)

    @staticmethod
    def _models_are_external(config: RuntimeBuilderConfig) -> bool:
        enabled = [item for item in (config.models or []) if item.get("enabled", True)]
        if not enabled:
            return False
        external_strategies = {"volume", "external-volume", "external_volume", "mounted"}
        return all(str(item.get("strategy") or "").lower() in external_strategies for item in enabled)

    @staticmethod
    def _modal_volume_path(config: RuntimeBuilderConfig) -> str:
        for volume in config.volumes or []:
            provider = str(volume.get("provider") or volume.get("type") or "").lower()
            if provider == "modal" or str(volume.get("name") or "").lower().startswith("modal"):
                configured = str(
                    volume.get("container_path")
                    or volume.get("mount_path")
                    or volume.get("path")
                    or RuntimeBuilderService.DEFAULT_MODAL_VOLUME_PATH
                ).rstrip("/")
                if configured in {"/app/ComfyUI/models", "/models"}:
                    return RuntimeBuilderService.DEFAULT_MODAL_VOLUME_PATH
                return configured
        return RuntimeBuilderService.DEFAULT_MODAL_VOLUME_PATH

    @staticmethod
    def _extra_model_paths_yaml(base_path: str) -> str:
        return "\n".join(
            [
                "tryon_modal_volume:",
                f"  base_path: {base_path}",
                "  checkpoints: checkpoints",
                "  clip: text_encoders",
                "  clip_vision: clip_vision",
                "  configs: configs",
                "  controlnet: controlnet",
                "  diffusion_models: |",
                "    diffusion_models",
                "    unet",
                "  embeddings: embeddings",
                "  gligen: gligen",
                "  hypernetworks: hypernetworks",
                "  loras: loras",
                "  photomaker: photomaker",
                "  style_models: style_models",
                "  text_encoders: text_encoders",
                "  upscale_models: upscale_models",
                "  vae: vae",
                "  vae_approx: vae_approx",
                "  sam3: sam3",
                "",
            ]
        )

    @staticmethod
    def _modal_app(volume_name: str, volume_path: str, runtime_name: str) -> str:
        # Docker Desktop and RunPod keep using scripts/startup.sh unchanged.
        # Modal starts ComfyUI directly after snapshot restoration and exposes
        # it through a small ASGI reverse proxy so long-lived WebSockets remain
        # stable behind Modal's web ingress.
        return f'''import asyncio
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

APP_NAME = {json.dumps(runtime_name)}
VOLUME_NAME = {json.dumps(volume_name)}
VOLUME_PATH = {json.dumps(volume_path)}
COMFYUI_PORT = 8188
STARTUP_TIMEOUT = int(os.getenv("TRYON_MODAL_STARTUP_TIMEOUT", "600"))

GPU = os.getenv("TRYON_MODAL_GPU", "L40S")
MIN_CONTAINERS = int(os.getenv("TRYON_MODAL_MIN_CONTAINERS", "0"))
MAX_CONTAINERS = int(os.getenv("TRYON_MODAL_MAX_CONTAINERS", "3"))
GENERATION_CONCURRENCY = int(os.getenv("TRYON_MODAL_CONCURRENCY", "1"))
INPUT_CONCURRENCY = int(os.getenv("TRYON_MODAL_INPUT_CONCURRENCY", "1000"))
SCALEDOWN_WINDOW = int(os.getenv("TRYON_MODAL_SCALEDOWN_WINDOW", "300"))
EXECUTION_TIMEOUT = int(os.getenv("TRYON_MODAL_EXECUTION_TIMEOUT", "1800"))

COMFYUI_ROOT = Path("/app/ComfyUI")
COMFYUI_MAIN = COMFYUI_ROOT / "main.py"
RUNTIME_ROOT = Path("/app/runtime")
MODELS_ROOT = Path(os.getenv("MODELS_ROOT", VOLUME_PATH))
COMFY_USER_ROOT = Path(os.getenv("COMFY_USER_ROOT", "/tmp/comfyui-user"))
COMFY_DATABASE_URL = os.getenv(
    "COMFY_DATABASE_URL",
    f"sqlite:///{{COMFY_USER_ROOT / 'comfyui.db'}}",
)

app = modal.App(APP_NAME)
models_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
image = modal.Image.from_dockerfile("Dockerfile.modal").pip_install("fastapi")


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
            print(f"[modal] ComfyUI listo en el puerto {{COMFYUI_PORT}}.", flush=True)
            return
        return_code = process.poll()
        if return_code is not None:
            raise RuntimeError(
                f"ComfyUI terminó antes de abrir el puerto {{COMFYUI_PORT}} "
                f"(código {{return_code}})."
            )
        time.sleep(1)
    raise TimeoutError(
        f"ComfyUI no abrió el puerto {{COMFYUI_PORT}} en {{timeout}} segundos."
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
    primary.write_text(machine_id + "\\n", encoding="utf-8")
    dbus.parent.mkdir(parents=True, exist_ok=True)
    dbus.write_text(machine_id + "\\n", encoding="utf-8")
    print(f"[runtime] Linux machine-id preparado para Execute Python: {{machine_id[:8]}}…", flush=True)


def _ensure_sam3_volume_link() -> None:
    """Expose the external SAM3 tree where TBG-SAM3 scans it directly."""
    source = MODELS_ROOT / "sam3"
    target = COMFYUI_ROOT / "models" / "sam3"

    if not source.is_dir():
        print(f"[runtime] SAM3 no enlazado: no existe el directorio {{source}}.", flush=True)
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        try:
            if target.resolve() == source.resolve():
                print(f"[runtime] SAM3 ya enlazado: {{target}} -> {{source}}", flush=True)
                return
        except OSError:
            pass
        target.unlink()
    elif target.exists():
        if target.is_dir() and not any(target.iterdir()):
            target.rmdir()
        else:
            raise RuntimeError(
                f"No se puede crear el enlace SAM3 porque {{target}} ya existe "
                "y contiene datos. No se eliminó ni sobrescribió nada."
            )

    target.symlink_to(source, target_is_directory=True)
    if not target.is_dir():
        raise RuntimeError(f"No se pudo crear el enlace SAM3: {{target}} -> {{source}}")
    print(f"[runtime] SAM3 enlazado desde el Volume: {{target}} -> {{source}}", flush=True)
    checkpoint = source / "sam3.pt"
    if not checkpoint.is_file():
        print(f"[runtime] Advertencia: no se encontró {{checkpoint}}.", flush=True)


def _prepare_runtime_directories() -> None:
    (COMFYUI_ROOT / "models").mkdir(parents=True, exist_ok=True)
    (COMFY_USER_ROOT / "default" / "workflows").mkdir(parents=True, exist_ok=True)
    _ensure_linux_machine_id()
    _ensure_sam3_volume_link()
    print(f"[runtime] Modelos externos registrados desde: {{MODELS_ROOT}}", flush=True)
    print(f"[runtime] Directorio temporal de usuario: {{COMFY_USER_ROOT}}", flush=True)


def _run_performance_probe(env: dict[str, str]) -> None:
    probe = RUNTIME_ROOT / "scripts" / "performance_probe.py"
    if not probe.is_file():
        return
    try:
        subprocess.run([sys.executable, str(probe)], env=env, check=False)
    except OSError as exc:
        print(f"[modal] No se pudo ejecutar performance_probe.py: {{exc}}", flush=True)


def _proxy_app():
    from aiohttp import ClientSession, WSMsgType
    from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
    from fastapi.responses import Response

    web_app = FastAPI()
    upstream_http = f"http://127.0.0.1:{{COMFYUI_PORT}}"
    upstream_ws = f"ws://127.0.0.1:{{COMFYUI_PORT}}"
    hop_headers = {{
        "connection", "keep-alive", "proxy-authenticate",
        "proxy-authorization", "te", "trailers",
        "transfer-encoding", "upgrade", "content-length",
    }}

    def clean_headers(headers):
        return {{k: v for k, v in headers.items() if k.lower() not in hop_headers and k.lower() != "host"}}

    def upstream_request_headers(headers):
        forwarded = clean_headers(headers)
        if any(key.lower() == "origin" for key in forwarded):
            forwarded["Origin"] = upstream_http
        if any(key.lower() == "referer" for key in forwarded):
            forwarded["Referer"] = f"{{upstream_http}}/"
        return forwarded

    @web_app.api_route("/{{path:path}}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
    async def proxy_http(path: str, request: Request):
        target = f"{{upstream_http}}/{{path}}"
        if request.url.query:
            target += f"?{{request.url.query}}"
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

    @web_app.websocket("/{{path:path}}")
    async def proxy_websocket(websocket: WebSocket, path: str):
        target = f"{{upstream_ws}}/{{path}}"
        query = websocket.scope.get("query_string", b"").decode("latin-1")
        if query:
            target += f"?{{query}}"
        websocket_handshake_headers = hop_headers | {{
            "host", "sec-websocket-key", "sec-websocket-version",
            "sec-websocket-extensions", "sec-websocket-protocol",
        }}
        forwarded = {{
            key.decode("latin-1"): value.decode("latin-1")
            for key, value in websocket.scope.get("headers", [])
            if key.decode("latin-1").lower() not in websocket_handshake_headers
        }}
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
                        elif message.type in {{WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR}}:
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

    return web_app


@app.cls(
    image=image,
    gpu=GPU,
    min_containers=MIN_CONTAINERS,
    max_containers=MAX_CONTAINERS,
    volumes={{VOLUME_PATH: models_volume}},
    timeout=EXECUTION_TIMEOUT,
    scaledown_window=SCALEDOWN_WINDOW,
    enable_memory_snapshot=True,
    experimental_options={{"enable_gpu_snapshot": True}},
)
@modal.concurrent(max_inputs=INPUT_CONCURRENCY)
class ComfyUIServer:
    def _start_process(self) -> None:
        if not COMFYUI_MAIN.is_file():
            raise RuntimeError(f"No se encontró ComfyUI en {{COMFYUI_MAIN}}.")

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
        print(f"[modal] Iniciando ComfyUI directamente: {{shlex.join(command)}}", flush=True)
        self.comfyui_process = subprocess.Popen(
            command,
            cwd=str(COMFYUI_ROOT),
            env=env,
            start_new_session=True,
        )
        _wait_until_ready(self.comfyui_process)

    @modal.enter(snap=True)
    def initialize_for_snapshot(self) -> None:
        os.environ["RUNTIME_PROVIDER"] = "modal"
        os.environ["COMFYUI_PORT"] = str(COMFYUI_PORT)
        print("[modal] Iniciando ComfyUI antes del snapshot de memoria.", flush=True)
        self._start_process()
        print(
            "[modal] ComfyUI inicializado y listo; creando snapshot de memoria.",
            flush=True,
        )

    @modal.enter(snap=False)
    def restore_after_snapshot(self) -> None:
        process = getattr(self, "comfyui_process", None)
        if process is None:
            raise RuntimeError(
                "El snapshot no restauró la referencia al proceso de ComfyUI."
            )

        return_code = process.poll()
        if return_code is not None:
            raise RuntimeError(
                f"ComfyUI no sobrevivió al restore del snapshot "
                f"(código {{return_code}})."
            )

        if _port_is_ready():
            print("[modal] ComfyUI restaurado desde snapshot y listo.", flush=True)
            return

        print(
            "[modal] Snapshot restaurado; esperando que ComfyUI reactive el puerto.",
            flush=True,
        )
        _wait_until_ready(process)
        print("[modal] ComfyUI restaurado desde snapshot y listo.", flush=True)

    @modal.asgi_app()
    def comfyui(self):
        return _proxy_app()

    @modal.exit()
    def shutdown(self) -> None:
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
'''

    @staticmethod
    def validate(config: RuntimeBuilderConfig) -> dict:
        issues: list[ValidationIssue] = []
        runtime_name = RuntimeBuilderService.sanitize_runtime_name(getattr(config, "runtime_name", None))
        if runtime_name != str(getattr(config, "runtime_name", "") or ""):
            issues.append(ValidationIssue("error", "runtime_name", f"El nombre debe usar formato Docker seguro. Sugerencia: {runtime_name}"))
        if not str(config.pytorch_index_url).rstrip("/").endswith("cu128"):
            issues.append(ValidationIssue("warning", "pytorch_index_url", "Para compatibilidad amplia con RTX 5090 y Modal se recomienda el índice cu128."))
        if RuntimeBuilderService.normalize_cuda_version(config.cuda_version) < "12.8.0":
            issues.append(ValidationIssue("warning", "cuda_version", "Para RTX 5090 se recomienda CUDA 12.8 o superior."))
        if not config.comfyui_commit:
            issues.append(
                ValidationIssue(
                    "warning",
                    "comfyui_commit",
                    "Conviene fijar un commit de ComfyUI para builds reproducibles.",
                )
            )
        if ":" not in config.registry_image:
            issues.append(
                ValidationIssue(
                    "warning",
                    "registry_image",
                    "La imagen no contiene un tag explícito; se agregará la versión del runtime.",
                )
            )
        if not re.match(r"^\d+\.\d+\.\d+([-.][A-Za-z0-9.]+)?$", config.runtime_version):
            issues.append(
                ValidationIssue(
                    "error",
                    "runtime_version",
                    "La versión debe seguir un formato semántico, por ejemplo 1.0.0.",
                )
            )

        names: set[str] = set()
        for index, node in enumerate(RuntimeBuilderService.merge_required_custom_nodes(config.custom_nodes)):
            name = str(node.get("name", "")).strip().lower()
            if not node.get("enabled", True):
                continue
            if name in names:
                issues.append(
                    ValidationIssue(
                        "error",
                        f"custom_nodes.{index}.name",
                        "Existe un custom node duplicado.",
                    )
                )
            names.add(name)
            if not str(node.get("repository", "")).startswith(("https://", "git@")):
                issues.append(
                    ValidationIssue(
                        "error",
                        f"custom_nodes.{index}.repository",
                        "El repositorio del nodo no es válido.",
                    )
                )
            if not node.get("commit"):
                issues.append(
                    ValidationIssue(
                        "warning",
                        f"custom_nodes.{index}.commit",
                        "El nodo no tiene commit fijo.",
                    )
                )

        enabled_models = [item for item in (config.models or []) if item.get("enabled", True)]
        for index, model in enumerate(enabled_models):
            if model.get("strategy") in {"image", "startup-download"} and not model.get("source_url"):
                issues.append(
                    ValidationIssue(
                        "error",
                        f"models.{index}.source_url",
                        "El modelo necesita una URL para esta estrategia.",
                    )
                )
            sha = model.get("sha256")
            if sha and not re.fullmatch(r"[a-fA-F0-9]{64}", sha):
                issues.append(
                    ValidationIssue(
                        "error",
                        f"models.{index}.sha256",
                        "SHA-256 debe contener 64 caracteres hexadecimales.",
                    )
                )

        for index, dependency in enumerate(config.python_dependencies or []):
            if not dependency.get("enabled", True):
                continue
            try:
                RuntimeBuilderService.render_requirement(dependency)
            except ValueError as exc:
                issues.append(
                    ValidationIssue(
                        "error",
                        f"python_dependencies.{index}",
                        str(exc),
                    )
                )

        if RuntimeBuilderService._is_modal(config) and RuntimeBuilderService._models_are_external(config):
            if not config.volumes:
                issues.append(
                    ValidationIssue(
                        "error",
                        "volumes",
                        "Modal con modelos externos necesita un Volume configurado.",
                    )
                )

        return {
            "valid": not any(issue.level == "error" for issue in issues),
            "issues": [asdict(issue) for issue in issues],
            "summary": {
                "custom_nodes": len(
                    [n for n in RuntimeBuilderService.merge_required_custom_nodes(config.custom_nodes) if n.get("enabled", True)]
                ),
                "models": len(enabled_models),
                "python_dependencies": len(
                    [d for d in (config.python_dependencies or []) if d.get("enabled", True)]
                ),
                "volumes": len(config.volumes or []),
                "reproducible": bool(config.comfyui_commit)
                and all(
                    bool(n.get("commit"))
                    for n in RuntimeBuilderService.merge_required_custom_nodes(config.custom_nodes)
                    if n.get("enabled", True)
                ),
            },
        }

    @staticmethod
    def generate(
        config: RuntimeBuilderConfig,
        modal_volume_name: str | None = None,
    ) -> dict:
        validation = RuntimeBuilderService.validate(config)
        if not validation["valid"]:
            errors = [item["message"] for item in validation["issues"] if item["level"] == "error"]
            raise ValueError("No se puede generar el runtime: " + " | ".join(errors))

        nodes = [n for n in RuntimeBuilderService.merge_required_custom_nodes(config.custom_nodes) if n.get("enabled", True)]
        deps = [d for d in (config.python_dependencies or []) if d.get("enabled", True)]
        models = [m for m in (config.models or []) if m.get("enabled", True)]

        node_lines: list[str] = []
        for node in nodes:
            folder = re.sub(r"[^A-Za-z0-9_.-]", "-", node["name"]).strip("-")
            node_lines.append(
                f"RUN git clone {node['repository']} /app/ComfyUI/custom_nodes/{folder}"
            )
            if node.get("commit"):
                node_lines.append(
                    f"RUN git -C /app/ComfyUI/custom_nodes/{folder} checkout {node['commit']}"
                )
            if node.get("install_requirements", True):
                node_lines.append(
                    "RUN if [ -f /app/ComfyUI/custom_nodes/"
                    f"{folder}/requirements.txt ]; then sed -Ei '/^(torch|torchvision|torchaudio|xformers|triton|onnxruntime-gpu|flash-attn)([<>=!~ ;]|$)/Id' "
                    f"/app/ComfyUI/custom_nodes/{folder}/requirements.txt && python -m pip install --no-cache-dir --constraint /tmp/runtime-constraints.txt -r "
                    f"/app/ComfyUI/custom_nodes/{folder}/requirements.txt; fi"
                )

        requirements = RuntimeBuilderService.render_requirements(deps)
        requirements_txt = "\n".join(requirements) + ("\n" if requirements else "")

        model_lines: list[str] = []
        for model in models:
            if model.get("strategy") == "image":
                model_lines.append(
                    "RUN mkdir -p $(dirname /app/ComfyUI/models/"
                    f"{model['target_path']}) && curl -fL '{model['source_url']}' "
                    f"-o /app/ComfyUI/models/{model['target_path']}"
                )

        modal_enabled = RuntimeBuilderService._is_modal(config)
        external_models = RuntimeBuilderService._models_are_external(config)
        volume_path = RuntimeBuilderService._modal_volume_path(config)
        extra_paths_copy = ""
        if modal_enabled and external_models:
            extra_paths_copy = "COPY runtime-builder/extra_model_paths.yaml /app/ComfyUI/extra_model_paths.yaml"

        commit_line = (
            f"RUN git -C /app/ComfyUI checkout {config.comfyui_commit}"
            if config.comfyui_commit
            else ""
        )
        dockerfile = "\n".join(
            filter(
                None,
                [
                    f"FROM nvidia/cuda:{RuntimeBuilderService.normalize_cuda_version(config.cuda_version)}-cudnn-runtime-ubuntu22.04",
                    'ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PATH="/opt/conda/bin:$PATH" TORCH_CUDA_ARCH_LIST="7.5;8.0;8.6;8.9;9.0;10.0;12.0"',
                    "RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git curl bzip2 ffmpeg libgl1 libopengl0 libglib2.0-0 build-essential pkg-config libgeos-dev libgdal-dev libcairo2-dev libjpeg-dev libpng-dev libtiff-dev libavcodec-dev libavdevice-dev libavfilter-dev libavformat-dev libavutil-dev libswresample-dev libswscale-dev && rm -rf /var/lib/apt/lists/*",
                    "RUN geos-config --version && ldconfig -p | grep -F libgeos_c.so",
                    "RUN curl -fL https://github.com/conda-forge/miniforge/releases/download/26.3.2-3/Miniforge3-26.3.2-3-Linux-x86_64.sh -o /tmp/miniforge.sh && echo '848194851a98903134187fbb4ab50efe87b003e0c0f808f97644b7524a62bf2c  /tmp/miniforge.sh' | sha256sum -c - && bash /tmp/miniforge.sh -b -p /opt/conda && rm /tmp/miniforge.sh && conda install -y python=3.11 pip && conda clean -afy",
                    "RUN python --version && python -m pip install --upgrade 'pip>=25,<26' setuptools wheel",
                    f"RUN git clone {config.comfyui_repository} /app/ComfyUI",
                    commit_line,
                    f"RUN python -m pip install --index-url {config.pytorch_index_url} torch torchvision torchaudio",
                    "RUN printf '%s\\n' 'transformers>=4.50.3,<5' > /tmp/runtime-constraints.txt && sed -Ei 's/^transformers.*$/transformers>=4.50.3,<5/I; /^(torch|torchvision|torchaudio|xformers|triton|onnxruntime-gpu|flash-attn)([<>=!~ ;]|$)/Id' /app/ComfyUI/requirements.txt && python -m pip install --constraint /tmp/runtime-constraints.txt -r /app/ComfyUI/requirements.txt",
                    *node_lines,
                    "COPY runtime-builder/requirements.txt /tmp/runtime-requirements.txt",
                    "RUN if [ -s /tmp/runtime-requirements.txt ]; then python -m pip install --constraint /tmp/runtime-constraints.txt -r /tmp/runtime-requirements.txt; fi",
                    'RUN set -eu; check_output="$(python -m pip check 2>&1)" && { printf \'%s\\n\' "$check_output"; exit 0; }; check_status=$?; printf \'%s\\n\' "$check_output"; unexpected="$(printf \'%s\\n\' "$check_output" | sed -E \'/^decord 0\\.6\\.0 is not supported on this platform$/d; /^[[:space:]]*$/d\')"; if [ -n "$unexpected" ]; then echo \'[runtime] pip check encontró errores no permitidos.\' >&2; exit "$check_status"; fi; echo \'[runtime] Advertencia conocida ignorada: decord 0.6.0 no declara soporte para esta plataforma.\'',
                    "RUN python -c 'import sys, torch, transformers; assert sys.version_info[:2] == (3, 11); assert torch.version.cuda and torch.version.cuda.startswith(\"12.8\"); assert int(transformers.__version__.split(\".\")[0]) < 5; print(sys.version); print(torch.__version__, torch.version.cuda); print(transformers.__version__)'",
                    *model_lines,
                    extra_paths_copy,
                    "COPY runpod_worker /app/runtime/runpod_worker",
                    "WORKDIR /app/runtime/runpod_worker",
                    "RUN python -m pip install --constraint /tmp/runtime-constraints.txt -r requirements.txt",
                    "COPY runtime-builder/entrypoint.sh /app/runtime/entrypoint.sh",
                    "RUN chmod +x /app/runtime/entrypoint.sh",
                    'ENTRYPOINT ["/app/runtime/entrypoint.sh"]',
                ],
            )
        ) + "\n"

        comfy_args = "--listen 0.0.0.0 --port 8188" if modal_enabled else "--listen 127.0.0.1 --port 8188"
        health_port = 8188
        entrypoint = f"""#!/usr/bin/env bash
set -euo pipefail

# Modal ejecuta su propio runtime pasando el comando como argumentos al
# ENTRYPOINT de la imagen. Debemos cederle el control con exec "$@"; de lo
# contrario este script inicia ComfyUI por su cuenta y el lifecycle de
# modal_app.py nunca llega a ejecutarse. En Docker Desktop/RunPod normalmente
# no se pasan argumentos, por lo que se conserva el flujo tradicional.
if [ "$#" -gt 0 ]; then
  echo "[runtime] Delegando el proceso al runtime de Modal/Docker: $*"
  exec "$@"
fi

MODELS_ROOT="${{MODELS_ROOT:-/models}}"
WORKFLOWS_ROOT="${{WORKFLOWS_ROOT:-/workflows}}"
COMFY_USER_ROOT="${{COMFY_USER_ROOT:-$WORKFLOWS_ROOT}}"
mkdir -p /app/ComfyUI/models "$COMFY_USER_ROOT/default/workflows"
echo "[runtime] Modelos externos registrados desde: $MODELS_ROOT"
echo "[runtime] Workflows persistentes registrados en: $COMFY_USER_ROOT/default/workflows"
python - <<'PY_RUNTIME_PROBE' || true
import importlib.util, json, os
report = {{"provider": os.getenv("RUNTIME_PROVIDER", "docker")}}
try:
    import torch
    report.update({{"pytorch": torch.__version__, "cuda_runtime": torch.version.cuda, "cuda_available": torch.cuda.is_available(), "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None, "capability": list(torch.cuda.get_device_capability(0)) if torch.cuda.is_available() else None}})
except Exception as exc:
    report["torch_error"] = str(exc)
for module in ("flash_attn", "xformers", "triton"):
    report[module] = importlib.util.find_spec(module) is not None
print("[runtime-performance] " + json.dumps(report, ensure_ascii=False, sort_keys=True))
PY_RUNTIME_PROBE
read -r -a EXTRA_ARGS <<< "${{COMFYUI_EXTRA_ARGS:-}}"
python /app/ComfyUI/main.py {comfy_args} --user-directory "$COMFY_USER_ROOT" "${{EXTRA_ARGS[@]}}" &
COMFY_PID=$!
for _ in $(seq 1 600); do
  curl -fsS http://127.0.0.1:{health_port}/system_stats >/dev/null && break
  sleep 1
done
if [ -f /app/runtime/runpod_worker/handler.py ] && [ "${{RUNTIME_PROVIDER:-}}" != "modal" ]; then
  python /app/runtime/runpod_worker/handler.py
fi
wait $COMFY_PID
"""

        runtime_manifest = {
            "contract": "runtime-builder/v2",
            "runtime_name": RuntimeBuilderService.sanitize_runtime_name(config.runtime_name),
            "gpu_profile": "universal-cu128",
            "gpu_targets": ["RTX 5090", "L4", "L40S", "A10G", "A100", "H100", "H200"],
            "name": config.name,
            "version": config.runtime_version,
            "platform": config.target_platform,
            "registry_image": config.registry_image,
            "comfyui": {
                "repository": config.comfyui_repository,
                "commit": config.comfyui_commit,
                "version": RuntimeBuilderService.RECOMMENDED_PROFILE["comfyui_version"],
                "frontend_version": RuntimeBuilderService.RECOMMENDED_PROFILE["comfyui_frontend_version"],
            },
            "compatibility_profile": RuntimeBuilderService.RECOMMENDED_PROFILE,
            "python": config.python_version,
            "cuda": config.cuda_version,
            "volumes": config.volumes or [],
            "provider": "modal" if modal_enabled else "docker",
            "model_storage": "external-volume" if external_models else "bundled",
        }
        custom_nodes_lock = {"nodes": nodes}
        models_manifest = {"models": models}
        env_example = (
            "\n".join(
                f"{item['key']}={'' if item.get('secret') else (item.get('value') or '')}"
                for item in (config.environment_variables or [])
            )
            + "\n"
        )

        result = {
            "dockerfile": dockerfile,
            "entrypoint": entrypoint,
            "requirements_txt": requirements_txt,
            "runtime_manifest": runtime_manifest,
            "custom_nodes_lock": custom_nodes_lock,
            "models_manifest": models_manifest,
            "env_example": env_example,
        }

        if modal_enabled:
            volume_name = str(modal_volume_name or "").strip()
            if not volume_name:
                volume_name = f"{RuntimeBuilderService.sanitize_runtime_name(config.runtime_name)}-models"
                for volume in config.volumes or []:
                    if volume.get("name"):
                        volume_name = str(volume["name"])
                        break
            result["modal_app"] = RuntimeBuilderService._modal_app(volume_name, volume_path, RuntimeBuilderService.sanitize_runtime_name(config.runtime_name))
            if external_models:
                result["extra_model_paths"] = RuntimeBuilderService._extra_model_paths_yaml(
                    volume_path
                )

        return result
