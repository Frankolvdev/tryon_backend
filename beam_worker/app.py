from __future__ import annotations

import os
import sys

from beam import Image, Volume, task_queue

sys.path.insert(0, "/app/runtime/runpod_worker")
from generation_runtime import GenerationRuntime

IMAGE_URI=os.environ.get("TRYON_BEAM_IMAGE_URI", "")
VOLUME_NAME=os.environ.get("TRYON_BEAM_VOLUME_NAME", "tryon-models")
VOLUME_PATH=os.environ.get("TRYON_BEAM_VOLUME_PATH", "/models")
image=Image.from_registry(IMAGE_URI)
runtime=GenerationRuntime()

@task_queue(
    name=os.environ.get("TRYON_BEAM_DEPLOYMENT_NAME", "tryon-generation-runtime"),
    image=image,
    gpu=os.environ.get("TRYON_BEAM_GPU", "H100"),
    cpu=float(os.environ.get("TRYON_BEAM_CPU", "8")),
    memory=int(os.environ.get("TRYON_BEAM_MEMORY_MB", "65536")),
    workers=int(os.environ.get("TRYON_BEAM_WORKERS", "1")),
    keep_warm_seconds=int(os.environ.get("TRYON_BEAM_KEEP_WARM_SECONDS", "10")),
    max_pending_tasks=int(os.environ.get("TRYON_BEAM_MAX_PENDING_TASKS", "100")),
    timeout=int(os.environ.get("TRYON_BEAM_TIMEOUT", "900")),
    retries=int(os.environ.get("TRYON_BEAM_RETRIES", "2")),
    volumes=[Volume(name=VOLUME_NAME,mount_path=VOLUME_PATH)],
    checkpoint_enabled=os.environ.get("TRYON_BEAM_CHECKPOINT", "false").lower() in {"1","true","yes","on"},
)
def handler(**payload):
    return runtime.execute(payload)
