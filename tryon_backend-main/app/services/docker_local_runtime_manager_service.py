from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import subprocess
import threading
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class DockerLocalRuntimeManagerService:
    """Small, isolated lifecycle manager for Runtime Builder Docker images.

    The service has no knowledge of queues, billing, FIFO, pricing, generation
    state or provider accounting. Its only contract is:
      selected Runtime Builder image -> healthy local ComfyUI URL.

    Docker performs host-port allocation atomically by publishing
    127.0.0.1::8188, therefore two managed images cannot claim the same host
    port. A container is reused by image tag when it is already healthy.
    """

    TARGET_PREFIX = "docker-local://"
    CONTAINER_PORT = 8188
    STARTUP_TIMEOUT_SECONDS = 180.0
    _lock = threading.RLock()

    @classmethod
    def target_for_image(cls, image_tag: str) -> str:
        raw = str(image_tag or "").strip()
        if not raw:
            raise ValueError("Docker image tag is required.")
        encoded = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
        return f"{cls.TARGET_PREFIX}{encoded}"

    @classmethod
    def is_managed_target(cls, value: str | None) -> bool:
        return str(value or "").startswith(cls.TARGET_PREFIX)

    @classmethod
    def image_from_target(cls, value: str | None) -> str:
        target = str(value or "").strip()
        if not cls.is_managed_target(target):
            raise ValueError("Docker Local target is not a managed Runtime Builder image.")
        encoded = target[len(cls.TARGET_PREFIX):]
        if not encoded:
            raise ValueError("Docker Local target has no image.")
        padding = "=" * ((4 - len(encoded) % 4) % 4)
        try:
            image = base64.urlsafe_b64decode((encoded + padding).encode("ascii")).decode("utf-8").strip()
        except Exception as exc:
            raise ValueError("Docker Local target is malformed.") from exc
        if not image:
            raise ValueError("Docker Local target has no image.")
        return image

    @staticmethod
    def _run(args: list[str], *, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                ["docker", *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("Docker CLI is not available on the Backend host.") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Docker command timed out: docker {' '.join(args[:3])}") from exc
        return result

    @classmethod
    def _require_ok(cls, result: subprocess.CompletedProcess[str], action: str) -> str:
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"{action} failed: {detail[-1800:] or 'Docker returned an error.'}")
        return (result.stdout or "").strip()

    @staticmethod
    def _safe_container_name(image_tag: str) -> str:
        digest = hashlib.sha256(image_tag.encode("utf-8")).hexdigest()[:12]
        readable = re.sub(r"[^a-z0-9]+", "-", image_tag.lower()).strip("-")[-36:] or "runtime"
        return f"tryon-local-{readable}-{digest}"[:63].rstrip("-")

    @staticmethod
    def _volume_name(prefix: str, image_tag: str) -> str:
        digest = hashlib.sha256(image_tag.encode("utf-8")).hexdigest()[:12]
        return f"{prefix}-{digest}"

    @staticmethod
    def _configured_models_volume() -> str:
        """Reuse the Runtime Builder model-export volume when configured.

        Read-only lookup. It does not mutate Runtime Builder configuration.
        """
        # Lazy imports keep the manager independent from DB initialization
        # until a container actually needs to be launched.
        from app.db.database import SessionLocal
        from app.models.runtime_builder_config import RuntimeBuilderConfig

        db = SessionLocal()
        try:
            config = (
                db.query(RuntimeBuilderConfig)
                .order_by(RuntimeBuilderConfig.is_active.desc(), RuntimeBuilderConfig.id.desc())
                .first()
            )
            if config is None:
                return "tryon-models"
            manifest = dict(config.last_export_manifest or {})
            mega3 = dict(manifest.get("mega3_settings") or {})
            export = dict(mega3.get("model_export") or {})
            configured = str(export.get("docker_volume") or "").strip()
            return configured or "tryon-models"
        except Exception:
            logger.exception("Could not read Runtime Builder model volume; using tryon-models.")
            return "tryon-models"
        finally:
            db.close()

    @classmethod
    def _image_id(cls, image_tag: str) -> str:
        result = cls._run(["image", "inspect", image_tag, "--format", "{{.Id}}"])
        return cls._require_ok(
            result,
            f"Docker Local image '{image_tag}' is not available locally",
        )

    @classmethod
    def _inspect_container(cls, name: str) -> dict[str, Any] | None:
        result = cls._run(["inspect", name])
        if result.returncode != 0:
            return None
        try:
            parsed = json.loads(result.stdout)
            return dict(parsed[0]) if isinstance(parsed, list) and parsed else None
        except Exception as exc:
            raise RuntimeError(f"Docker returned invalid inspect data for {name}.") from exc

    @classmethod
    def _endpoint_from_inspect(cls, info: dict[str, Any]) -> str | None:
        ports = (
            dict(info.get("NetworkSettings") or {})
            .get("Ports", {})
            .get(f"{cls.CONTAINER_PORT}/tcp")
        )
        if not isinstance(ports, list) or not ports:
            return None
        host_port = str((ports[0] or {}).get("HostPort") or "").strip()
        if not host_port.isdigit():
            return None
        return f"http://127.0.0.1:{host_port}"

    @staticmethod
    def _running(info: dict[str, Any]) -> bool:
        return bool(dict(info.get("State") or {}).get("Running"))

    @staticmethod
    def _container_image_id(info: dict[str, Any]) -> str:
        return str(info.get("Image") or "").strip()

    @staticmethod
    def _healthy(endpoint: str, *, timeout: float = 2.5) -> bool:
        try:
            response = httpx.get(f"{endpoint.rstrip('/')}/system_stats", timeout=timeout)
            return response.is_success
        except Exception:
            return False

    @classmethod
    def _wait_healthy(cls, endpoint: str, container_name: str) -> str:
        deadline = time.monotonic() + cls.STARTUP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if cls._healthy(endpoint):
                return endpoint
            time.sleep(1.0)
        logs = cls._run(["logs", "--tail", "80", container_name], timeout=15.0)
        detail = ((logs.stdout or "") + "\n" + (logs.stderr or "")).strip()
        raise RuntimeError(
            "Docker Local container started but ComfyUI did not become ready. "
            f"Container: {container_name}. Logs: {detail[-3000:]}"
        )

    @classmethod
    def _remove_container(cls, name: str) -> None:
        cls._run(["rm", "-f", name], timeout=30.0)

    @classmethod
    def _create_container(cls, image_tag: str, name: str) -> dict[str, Any]:
        models_volume = cls._configured_models_volume()
        workflows_volume = cls._volume_name("tryon-workflows", image_tag)
        output_volume = cls._volume_name("tryon-output", image_tag)
        image_hash = hashlib.sha256(image_tag.encode("utf-8")).hexdigest()

        # Empty host port means Docker selects an unused port atomically.
        args = [
            "run", "-d",
            "--restart", "unless-stopped",
            "--name", name,
            "--label", "tryon.local-runtime-managed=true",
            "--label", f"tryon.local-runtime-image={image_hash}",
            "--gpus", "all",
            "-p", f"127.0.0.1::{cls.CONTAINER_PORT}",
            "-v", f"{models_volume}:/models",
            "-v", f"{workflows_volume}:/workflows",
            "-v", f"{output_volume}:/app/ComfyUI/output",
            image_tag,
        ]
        cls._require_ok(cls._run(args, timeout=90.0), f"Starting Docker Local runtime '{image_tag}'")
        info = cls._inspect_container(name)
        if info is None:
            raise RuntimeError(f"Docker Local container '{name}' disappeared after startup.")
        return info

    @classmethod
    def ensure_endpoint(cls, target: str) -> str:
        image_tag = cls.image_from_target(target)

        with cls._lock:
            expected_image_id = cls._image_id(image_tag)
            name = cls._safe_container_name(image_tag)
            info = cls._inspect_container(name)

            # A mutable tag may have been rebuilt. Never silently keep a
            # container running the old image under the same tag.
            if info is not None and cls._container_image_id(info) != expected_image_id:
                cls._remove_container(name)
                info = None

            if info is not None and not cls._running(info):
                started = cls._run(["start", name], timeout=45.0)
                if started.returncode != 0:
                    cls._remove_container(name)
                    info = None
                else:
                    info = cls._inspect_container(name)

            if info is None:
                info = cls._create_container(image_tag, name)

            endpoint = cls._endpoint_from_inspect(info)
            if not endpoint:
                # Existing managed container without the expected publication
                # is stale; recreate it rather than guessing a port.
                cls._remove_container(name)
                info = cls._create_container(image_tag, name)
                endpoint = cls._endpoint_from_inspect(info)

            if not endpoint:
                raise RuntimeError("Docker Local did not publish a ComfyUI host port.")

            if cls._healthy(endpoint):
                return endpoint

            # One bounded restart before rebuilding the managed container.
            cls._run(["restart", name], timeout=45.0)
            info = cls._inspect_container(name) or {}
            endpoint = cls._endpoint_from_inspect(info) or endpoint
            try:
                return cls._wait_healthy(endpoint, name)
            except RuntimeError:
                cls._remove_container(name)
                info = cls._create_container(image_tag, name)
                endpoint = cls._endpoint_from_inspect(info)
                if not endpoint:
                    raise RuntimeError("Docker Local did not publish a ComfyUI host port.")
                return cls._wait_healthy(endpoint, name)


docker_local_runtime_manager_service = DockerLocalRuntimeManagerService()
