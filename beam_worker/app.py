from __future__ import annotations

import os
import sys
from typing import Any

from beam import Image, QueueDepthAutoscaler, Volume, task_queue

sys.path.insert(0, "/app/runtime/runpod_worker")
from generation_runtime import GenerationRuntime


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


IMAGE_URI = os.environ.get("TRYON_BEAM_IMAGE_URI", "").strip()
VOLUME_NAME = os.environ.get("TRYON_BEAM_VOLUME_NAME", "tryon-models").strip()
VOLUME_PATH = os.environ.get("TRYON_BEAM_VOLUME_PATH", "/models").strip()
DEPLOYMENT_NAME = os.environ.get("TRYON_BEAM_DEPLOYMENT_NAME", "tryon-generation-runtime").strip()

if not IMAGE_URI:
    raise RuntimeError("TRYON_BEAM_IMAGE_URI is required for the Beam deployment.")

image = Image.from_registry(IMAGE_URI)
volumes = [Volume(name=VOLUME_NAME, mount_path=VOLUME_PATH)] if VOLUME_NAME else []


def start_runtime() -> dict[str, Any]:
    """Beam equivalent of Modal container startup.

    This executes once when a container starts. When checkpoints are enabled,
    Beam captures the container after this function finishes, so the runtime is
    restored already initialized on subsequent cold starts.
    """
    return {"runtime": GenerationRuntime()}


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
def handler(context: Any, **payload: Any) -> dict[str, Any]:
    runtime = None
    if isinstance(context, dict):
        runtime = context.get("runtime")
    if runtime is None:
        # Defensive fallback for SDK/runtime versions that wrap on_start data.
        on_start_value = getattr(context, "on_start_value", None)
        if isinstance(on_start_value, dict):
            runtime = on_start_value.get("runtime")
    if runtime is None:
        runtime = GenerationRuntime()
    return runtime.execute(payload)
