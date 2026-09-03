from __future__ import annotations

import atexit
import json
import mimetypes
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from beam import Image, Output, QueueDepthAutoscaler, Volume, env, task_queue


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


BASE_IMAGE = os.environ.get("TRYON_BEAM_BASE_IMAGE", "").strip()
DOCKERFILE = os.environ.get("TRYON_BEAM_DOCKERFILE", "./Dockerfile").strip()
CONTEXT_DIR = os.environ.get("TRYON_BEAM_CONTEXT_DIR", ".").strip()
VOLUME_NAME = os.environ.get("TRYON_BEAM_VOLUME_NAME", "tryon-models").strip()
VOLUME_PATH = os.environ.get("TRYON_BEAM_VOLUME_PATH", "/models").strip()
DEPLOYMENT_NAME = os.environ.get(
    "TRYON_BEAM_DEPLOYMENT_NAME", "tryon-generation-runtime"
).strip()

if BASE_IMAGE:
    # Configuration-only redeploy: reuse the exact published runtime image.
    # This avoids syncing/building ComfyUI and custom_nodes again.
    image = Image(base_image=BASE_IMAGE)
else:
    if not DOCKERFILE:
        raise RuntimeError(
            "TRYON_BEAM_DOCKERFILE is required when TRYON_BEAM_BASE_IMAGE is empty."
        )
    # Full runtime build path, used only when an image has not been published yet.
    image = Image().from_dockerfile(DOCKERFILE, CONTEXT_DIR)
volumes = [Volume(name=VOLUME_NAME, mount_path=VOLUME_PATH)] if VOLUME_NAME else []


_EXPECTED_MODEL_DIRS = (
    "checkpoints",
    "clip_vision",
    "configs",
    "controlnet",
    "diffusion_models",
    "embeddings",
    "gligen",
    "hypernetworks",
    "loras",
    "photomaker",
    "sam3",
    "style_models",
    "text_encoders",
    "unet",
    "upscale_models",
    "vae",
    "vae_approx",
)


def _validate_direct_model_volume() -> None:
    """Validate the configured Beam Volume without inventing nested model roots."""
    root = Path(VOLUME_PATH)
    if not VOLUME_NAME:
        raise RuntimeError("Beam volume_name is empty in provider configuration.")
    if not root.is_dir():
        raise RuntimeError(
            f"Beam did not mount configured volume {VOLUME_NAME!r} at {VOLUME_PATH!r}."
        )

    try:
        entries = sorted(item.name for item in root.iterdir())
    except OSError as exc:
        raise RuntimeError(
            f"Could not inspect Beam volume {VOLUME_NAME!r} at {VOLUME_PATH!r}: {exc}"
        ) from exc

    present = [name for name in _EXPECTED_MODEL_DIRS if (root / name).is_dir()]
    print(
        f"[beam-runtime] Volumen configurado: {VOLUME_NAME} -> {VOLUME_PATH}",
        flush=True,
    )
    print(
        "[beam-runtime] Contenido raíz del volumen: "
        + (", ".join(entries[:80]) if entries else "<vacío>"),
        flush=True,
    )
    if not present:
        raise RuntimeError(
            f"El volumen Beam configurado {VOLUME_NAME!r} está montado en "
            f"{VOLUME_PATH!r}, pero no contiene carpetas de modelos en su raíz. "
            "Se esperaba, por ejemplo, vae/, text_encoders/, unet/ o sam3/. "
            f"Contenido encontrado: {entries[:80]!r}"
        )

    print(
        "[beam-runtime] Carpetas de modelos detectadas directamente: "
        + ", ".join(present),
        flush=True,
    )


COMFYUI_ROOT = Path("/app/ComfyUI")
COMFYUI_MAIN = COMFYUI_ROOT / "main.py"
COMFYUI_PORT = int(os.environ.get("TRYON_BEAM_COMFYUI_PORT", "8188"))
COMFYUI_URL = f"http://127.0.0.1:{COMFYUI_PORT}"
COMFY_USER_ROOT = Path(os.environ.get("TRYON_BEAM_COMFY_USER_ROOT", "/workflows"))
COMFY_DATABASE_URL = os.environ.get(
    "TRYON_BEAM_COMFY_DATABASE_URL",
    f"sqlite:///{COMFY_USER_ROOT / 'comfyui.db'}",
).strip()
_COMFYUI_PROCESS: subprocess.Popen[Any] | None = None


def _write_extra_model_paths() -> None:
    """Register the Beam Volume using the same logical model map as Modal."""
    comfy_root = Path("/app/ComfyUI")
    comfy_root.mkdir(parents=True, exist_ok=True)
    content = "\n".join(
        [
            "tryon_beam_volume:",
            f"  base_path: {VOLUME_PATH}",
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
    target = comfy_root / "extra_model_paths.yaml"
    target.write_text(content, encoding="utf-8")
    print(f"[beam-runtime] Rutas de modelos registradas: {target} -> {VOLUME_PATH}", flush=True)


def _ensure_linux_machine_id() -> None:
    """Provide the stable Linux machine-id expected by ComfyUI Execute Python."""
    primary = Path("/etc/machine-id")
    dbus = Path("/var/lib/dbus/machine-id")

    machine_id = ""
    for candidate_path in (primary, dbus):
        if not candidate_path.is_file():
            continue
        try:
            candidate = candidate_path.read_text(encoding="utf-8").strip().lower()
        except OSError:
            continue
        if len(candidate) == 32 and all(char in "0123456789abcdef" for char in candidate):
            machine_id = candidate
            break

    if not machine_id:
        machine_id = uuid.uuid4().hex

    for target in (primary, dbus):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(machine_id + "\n", encoding="utf-8")

    print(
        f"[beam-runtime] Linux machine-id preparado para Execute Python: {machine_id[:8]}…",
        flush=True,
    )


def _ensure_sam3_volume_link() -> None:
    """Expose the complete SAM3 tree where TBG-SAM3 scans it directly."""
    source = Path(VOLUME_PATH) / "sam3"
    target = Path("/app/ComfyUI/models/sam3")
    if not source.is_dir():
        print(f"[beam-runtime] SAM3 no enlazado: no existe {source}.", flush=True)
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        try:
            if target.resolve() == source.resolve():
                print(f"[beam-runtime] SAM3 ya enlazado: {target} -> {source}", flush=True)
                return
        except OSError:
            pass
        target.unlink()
    elif target.exists():
        if target.is_dir() and not any(target.iterdir()):
            target.rmdir()
        else:
            raise RuntimeError(
                f"No se puede enlazar SAM3: {target} ya existe y contiene datos; "
                "Beam no eliminó ni sobrescribió nada."
            )

    target.symlink_to(source, target_is_directory=True)
    if not target.is_dir():
        raise RuntimeError(f"No se pudo crear el enlace SAM3: {target} -> {source}")
    print(f"[beam-runtime] SAM3 enlazado desde el Volume: {target} -> {source}", flush=True)
    checkpoint = source / "sam3.pt"
    if not checkpoint.is_file():
        print(f"[beam-runtime] Advertencia: no se encontró {checkpoint}.", flush=True)


def _prepare_beam_runtime() -> None:
    # The configured Beam Volume is mounted directly at VOLUME_PATH. Its root
    # contains vae/, text_encoders/, unet/, sam3/, etc.; no nested models/
    # directory is invented or auto-detected.
    os.environ["MODELS_ROOT"] = VOLUME_PATH
    _validate_direct_model_volume()
    _ensure_linux_machine_id()
    _write_extra_model_paths()
    _ensure_sam3_volume_link()


def _terminate_comfyui() -> None:
    global _COMFYUI_PROCESS
    process = _COMFYUI_PROCESS
    _COMFYUI_PROCESS = None
    if process is None or process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=15)
    except Exception:
        try:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except Exception:
            pass


def _interrupt_comfyui() -> None:
    try:
        request = urllib.request.Request(f"{COMFYUI_URL}/interrupt", data=b"{}", method="POST")
        request.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(request, timeout=5):
            pass
    except Exception:
        pass


def _wait_for_comfyui(process: subprocess.Popen[Any], timeout_seconds: int = 300) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"ComfyUI terminó durante el arranque con código {process.returncode}.")
        try:
            with urllib.request.urlopen(f"{COMFYUI_URL}/system_stats", timeout=5) as response:
                if 200 <= response.status < 300:
                    print(f"[beam-runtime] ComfyUI listo en {COMFYUI_URL}.", flush=True)
                    return
        except Exception as error:
            last_error = error
        time.sleep(1)
    _terminate_comfyui()
    raise TimeoutError(f"ComfyUI no quedó disponible en {COMFYUI_URL}: {last_error}")


def _start_comfyui() -> subprocess.Popen[Any]:
    global _COMFYUI_PROCESS
    if _COMFYUI_PROCESS is not None and _COMFYUI_PROCESS.poll() is None:
        return _COMFYUI_PROCESS
    if not COMFYUI_MAIN.is_file():
        raise RuntimeError(f"No se encontró ComfyUI en {COMFYUI_MAIN}.")
    COMFY_USER_ROOT.mkdir(parents=True, exist_ok=True)
    (COMFY_USER_ROOT / "default" / "workflows").mkdir(parents=True, exist_ok=True)
    env_vars = os.environ.copy()
    env_vars.update({
        "RUNTIME_PROVIDER": "beam",
        "COMFYUI_PORT": str(COMFYUI_PORT),
        "MODELS_ROOT": VOLUME_PATH,
        "COMFY_USER_ROOT": str(COMFY_USER_ROOT),
        "COMFY_DATABASE_URL": COMFY_DATABASE_URL,
        "COMFYUI_URL": COMFYUI_URL,
    })
    extra_args = shlex.split(env_vars.get("COMFYUI_EXTRA_ARGS", ""))
    command = [
        sys.executable, str(COMFYUI_MAIN),
        "--listen", "127.0.0.1",
        "--port", str(COMFYUI_PORT),
        "--user-directory", str(COMFY_USER_ROOT),
        "--database-url", COMFY_DATABASE_URL,
        *extra_args,
    ]
    print(f"[beam-runtime] Iniciando ComfyUI: {shlex.join(command)}", flush=True)
    _COMFYUI_PROCESS = subprocess.Popen(
        command, cwd=str(COMFYUI_ROOT), env=env_vars,
        start_new_session=(os.name != "nt"),
    )
    _wait_for_comfyui(_COMFYUI_PROCESS)
    return _COMFYUI_PROCESS


def _publish_generation_files(value: Any) -> Any:
    if isinstance(value, dict):
        if value.get("__generation_file__") and value.get("local_path"):
            source = Path(str(value["local_path"]))
            if not source.is_file():
                raise RuntimeError(f"El resultado generado no existe: {source}")
            artifact_name = f"tryon-beam-file-{uuid.uuid4().hex}{source.suffix or '.bin'}"
            published_path = Path(tempfile.gettempdir()) / artifact_name
            published_path.write_bytes(source.read_bytes())
            Output(path=str(published_path)).save()
            enriched = dict(value)
            enriched.pop("local_path", None)
            enriched["beam_output_name"] = artifact_name
            enriched["filename"] = enriched.get("filename") or source.name
            enriched["content_type"] = enriched.get("content_type") or mimetypes.guess_type(source.name)[0] or "application/octet-stream"
            enriched["size_bytes"] = source.stat().st_size
            return enriched
        return {key: _publish_generation_files(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_publish_generation_files(item) for item in value]
    return value


atexit.register(_terminate_comfyui)


def _generation_runtime_class():
    # The generated Dockerfile contains this runtime under /app/runtime. Delay the
    # import until Beam executes remotely so the local deployment CLI only needs
    # to parse the application definition.
    sys.path.insert(0, "/app/runtime/runpod_worker")
    from generation_runtime import GenerationRuntime

    resolver = getattr(GenerationRuntime, "_resolve_dynamic_node_types", None)
    if not callable(resolver):
        raise RuntimeError(
            "Beam GenerationRuntime no contiene el remapeador dinámico de Execute Python."
        )
    return GenerationRuntime


def start_runtime() -> dict[str, Any]:
    _prepare_beam_runtime()
    _start_comfyui()
    generation_runtime = _generation_runtime_class()
    return {"runtime": generation_runtime(comfy_url=COMFYUI_URL)}


@task_queue(
    name=DEPLOYMENT_NAME,
    image=image,
    gpu=os.environ.get("TRYON_BEAM_GPU", "H100"),
    workers=int(os.environ.get("TRYON_BEAM_WORKERS", "1")),
    keep_warm_seconds=int(os.environ.get("TRYON_BEAM_KEEP_WARM_SECONDS", "10")),
    max_pending_tasks=int(os.environ.get("TRYON_BEAM_MAX_PENDING_TASKS", "100")),
    timeout=int(os.environ.get("TRYON_BEAM_TIMEOUT", "900")),
    retries=int(os.environ.get("TRYON_BEAM_RETRIES", "2")),
    callback_url=os.environ.get("TRYON_BEAM_CALLBACK_URL", "").strip() or None,
    authorized=_env_bool("TRYON_BEAM_AUTHORIZED", True),
    volumes=volumes,
    autoscaler=QueueDepthAutoscaler(
        min_containers=int(os.environ.get("TRYON_BEAM_MIN_CONTAINERS", "0")),
        max_containers=int(os.environ.get("TRYON_BEAM_MAX_CONTAINERS", "5")),
        tasks_per_container=int(os.environ.get("TRYON_BEAM_TASKS_PER_CONTAINER", "1")),
    ),
    on_start=start_runtime,
    checkpoint_enabled=_env_bool("TRYON_BEAM_CHECKPOINT", False),
)
def handler(
    context: Any,
    tryon_payload: dict[str, Any] | None = None,
    **legacy_payload: Any,
) -> dict[str, Any]:
    runtime = None
    if isinstance(context, dict):
        runtime = context.get("runtime")
    if runtime is None:
        on_start_value = getattr(context, "on_start_value", None)
        if isinstance(on_start_value, dict):
            runtime = on_start_value.get("runtime")
    if runtime is None:
        generation_runtime = _generation_runtime_class()
        runtime = generation_runtime()

    # New Beam submissions arrive inside ``tryon_payload`` to avoid colliding
    # with Beam's reserved ``context`` argument. Keep legacy kwargs support for
    # already queued tasks that do not contain a business field named context.
    payload = tryon_payload if isinstance(tryon_payload, dict) else legacy_payload
    try:
        result = runtime.execute(payload)
    except BaseException:
        _interrupt_comfyui()
        raise
    if not isinstance(result, dict):
        raise RuntimeError(
            f"Beam Generation Runtime returned {type(result).__name__}; expected a JSON object."
        )
    if str(result.get("status") or "").lower() == "failed":
        _interrupt_comfyui()
        raise RuntimeError(str(result.get("error") or "Beam Generation Runtime failed."))
    result = _publish_generation_files(result)

    # Beam Task Queues expose persisted Output files through the task-status API;
    # a normal Python return value is not included in the ``outputs`` array.
    result_path = Path(tempfile.gettempdir()) / f"tryon-beam-result-{uuid.uuid4().hex}.json"
    try:
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        Output(path=str(result_path)).save()
        print(f"[beam-runtime] Resultado publicado: {result_path.name}", flush=True)
    finally:
        try:
            result_path.unlink(missing_ok=True)
        except OSError:
            pass

    # The persisted JSON artifact is the authoritative asynchronous response.
    return {"output_artifact": result_path.name}
