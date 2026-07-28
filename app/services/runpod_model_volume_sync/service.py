from __future__ import annotations

import json
import shlex
import time
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from app.services.runpod_model_volume_sync.config import (
    RunPodModelVolumeSyncSettings,
    resolve_private_key_path,
)
from app.services.runpod_model_volume_sync.control_plane import RunPodModelSyncControlPlane
from app.services.runpod_model_volume_sync.transport import RsyncSshTransport, SshTarget

ProgressCallback = Callable[[str, int, str], None]


class RunPodModelVolumeSyncService:
    """Isolated RunPod destination for the existing model-volume exporter.

    Safety boundary: this class can create, inspect and delete only its temporary
    Pod. It has no Network Volume delete operation.
    """

    @staticmethod
    def _normalize_remote_path(value: str) -> str:
        normalized = str(value or "").replace("\\", "/").strip("/")
        parts = PurePosixPath(normalized).parts if normalized else ()
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("La ruta remota de RunPod contiene segmentos no permitidos.")
        return "/".join(parts)

    @staticmethod
    def _manifest(root: Path) -> dict[str, int]:
        return {
            item.relative_to(root).as_posix(): item.stat().st_size
            for item in sorted(root.rglob("*"), key=lambda p: p.as_posix().casefold())
            if item.is_file()
        }

    @staticmethod
    def _startup_command() -> list[str]:
        script = r"""
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends openssh-server rsync python3 ca-certificates
mkdir -p /run/sshd /root/.ssh
chmod 700 /root/.ssh
KEY_VALUE="${SSH_PUBLIC_KEY:-${PUBLIC_KEY:-}}"
if [ -z "$KEY_VALUE" ]; then
  echo 'No se recibió SSH_PUBLIC_KEY/PUBLIC_KEY' >&2
  exit 64
fi
printf '%s\n' "$KEY_VALUE" > /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
ssh-keygen -A
printf '%s\n' \
  'PermitRootLogin prohibit-password' \
  'PasswordAuthentication no' \
  'PubkeyAuthentication yes' \
  'ChallengeResponseAuthentication no' \
  > /etc/ssh/sshd_config.d/99-tryon-model-sync.conf
exec /usr/sbin/sshd -D -e
""".strip()
        return ["bash", "-lc", script]

    @classmethod
    def _pod_payload(cls, *, settings: RunPodModelVolumeSyncSettings, volume_id: str,
                     data_center_id: str, public_key: str) -> dict[str, Any]:
        return {
            "name": f"{settings.pod_name_prefix}-{int(time.time())}",
            "computeType": "CPU",
            "cloudType": "SECURE",
            "vcpuCount": settings.vcpu_count,
            "containerDiskInGb": settings.container_disk_gb,
            "imageName": settings.pod_image,
            "dockerEntrypoint": [],
            "dockerStartCmd": cls._startup_command(),
            "env": {"PUBLIC_KEY": public_key, "SSH_PUBLIC_KEY": public_key},
            "interruptible": False,
            "locked": False,
            "dataCenterIds": [data_center_id],
            "dataCenterPriority": "custom",
            "networkVolumeId": volume_id,
            "volumeInGb": 0,
            "volumeMountPath": settings.volume_mount_path,
            "ports": ["22/tcp"],
            "supportPublicIp": True,
        }

    @classmethod
    def _wait_for_target(cls, control: RunPodModelSyncControlPlane, pod_id: str, *, timeout: int,
                         poll_interval: int, notify: ProgressCallback) -> SshTarget:
        deadline = time.monotonic() + timeout
        last_status = ""
        while time.monotonic() < deadline:
            pod = control.get_pod(pod_id)
            status = str(pod.get("desiredStatus") or pod.get("status") or "inicializando")
            if status != last_status:
                notify("runpod-pod-starting", 95, f"Pod temporal: {status}")
                last_status = status
            host = str(pod.get("publicIp") or "").strip()
            mappings = pod.get("portMappings") or {}
            port = mappings.get("22") or mappings.get(22)
            if host and port:
                return SshTarget(host=host, port=int(port))
            time.sleep(poll_interval)
        raise RuntimeError("RunPod no asignó IP pública y puerto SSH al Pod temporal a tiempo.")

    @classmethod
    def _verify(cls, transport: RsyncSshTransport, target: SshTarget, remote_dir: str,
                manifest: dict[str, int], notify: ProgressCallback) -> None:
        notify("runpod-verifying", 98, "Verificando archivos y tamaños en el Network Volume…")
        encoded = json.dumps(manifest, separators=(",", ":"), ensure_ascii=False)
        script = (
            "python3 - <<'PY'\n"
            "import json, pathlib, sys\n"
            f"root=pathlib.Path({remote_dir!r})\n"
            f"expected=json.loads({encoded!r})\n"
            "errors=[]\n"
            "for rel,size in expected.items():\n"
            " p=root/rel\n"
            " if not p.is_file(): errors.append(f'FALTA: {rel}')\n"
            " elif p.stat().st_size != size: errors.append(f'TAMANO: {rel} local={size} remoto={p.stat().st_size}')\n"
            "if errors:\n"
            " print('\\n'.join(errors[:100]))\n"
            " sys.exit(3)\n"
            "print(f'OK {len(expected)} archivos')\n"
            "PY"
        )
        result = transport.ssh(target, script, timeout=1800, check=False)
        if result.returncode != 0:
            detail = (result.stdout or result.stderr or "verificación fallida").strip()
            raise RuntimeError(f"La verificación del Network Volume falló: {detail[-4000:]}")

    @classmethod
    def sync_tree(cls, *, api_key: str, volume_id: str, data_center_id: str,
                  models_root: Path, remote_path: str, overwrite: bool,
                  timeout_seconds: int, notify: ProgressCallback) -> dict[str, Any]:
        api_key = str(api_key or "").strip()
        volume_id = str(volume_id or "").strip()
        data_center_id = str(data_center_id or "").strip().upper()
        if not api_key:
            raise ValueError("Configura la API key de RunPod antes de exportar modelos.")
        if not volume_id:
            raise ValueError("Configura el Network Volume ID de RunPod.")
        if not data_center_id:
            raise ValueError("Configura el Data Center ID de RunPod.")
        if not models_root.is_dir():
            raise ValueError(f"No existe el directorio preparado de modelos: {models_root}")

        settings = RunPodModelVolumeSyncSettings.load()
        private_key = resolve_private_key_path()
        transport = RsyncSshTransport(private_key)
        control = RunPodModelSyncControlPlane(api_key)
        manifest = cls._manifest(models_root)
        if not manifest:
            raise ValueError("No hay modelos preparados para sincronizar con RunPod.")

        notify("runpod-validating", 94, "Validando Network Volume y Data Center de RunPod…")
        volume = control.get_volume(volume_id)
        volume_dc = str(volume.get("dataCenterId") or "").strip().upper()
        if volume_dc and volume_dc != data_center_id:
            raise ValueError(
                f"El Network Volume pertenece a {volume_dc}, pero el BackOffice tiene {data_center_id}."
            )

        relative = cls._normalize_remote_path(remote_path)
        remote_dir = settings.volume_mount_path.rstrip("/")
        if relative:
            remote_dir += "/" + relative

        pod_id = ""
        started = time.monotonic()
        primary_error: BaseException | None = None
        try:
            notify("runpod-pod-create", 95, "Creando Pod temporal económico para sincronizar modelos…")
            pod = control.create_pod(
                cls._pod_payload(
                    settings=settings,
                    volume_id=volume_id,
                    data_center_id=data_center_id,
                    public_key=transport.public_key(),
                )
            )
            pod_id = str(pod.get("id") or "").strip()
            if not pod_id:
                raise RuntimeError("RunPod creó una respuesta sin ID de Pod temporal.")
            target = cls._wait_for_target(
                control, pod_id,
                timeout=min(max(timeout_seconds, 60), settings.pod_ready_timeout_seconds),
                poll_interval=settings.poll_interval_seconds,
                notify=notify,
            )
            transport.wait_until_ready(
                target,
                timeout=settings.ssh_ready_timeout_seconds,
                poll_interval=settings.poll_interval_seconds,
                notify=notify,
            )
            transport.ssh(target, f"mkdir -p -- {shlex.quote(remote_dir)}", timeout=60)
            rsync_output = transport.rsync(
                models_root,
                target,
                remote_dir,
                overwrite=overwrite,
                timeout=settings.transfer_timeout_seconds,
                notify=notify,
            )
            cls._verify(transport, target, remote_dir, manifest, notify)
            return {
                "type": "runpod_network_volume",
                "transport": "ssh+rsync",
                "volume_id": volume_id,
                "data_center_id": data_center_id,
                "path": relative,
                "mount_path": settings.volume_mount_path,
                "files_verified": len(manifest),
                "bytes_verified": sum(manifest.values()),
                "overwrite_requested": bool(overwrite),
                "temporary_pod_id": pod_id,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "rsync_output": rsync_output[-4000:],
            }
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            cleanup_error: Exception | None = None
            if pod_id:
                try:
                    notify("runpod-pod-cleanup", 99, "Eliminando únicamente el Pod temporal…")
                    control.delete_pod(pod_id)
                except Exception as exc:
                    cleanup_error = exc
            transport.close()
            if cleanup_error is not None and primary_error is None:
                raise RuntimeError(
                    "La sincronización terminó, pero no fue posible eliminar el Pod temporal "
                    f"{pod_id}. El Network Volume NO fue eliminado. Error: {cleanup_error}"
                ) from cleanup_error
