from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunPodModelVolumeSyncSettings:
    """Internal settings for the isolated RunPod model-volume sync flow."""

    pod_image: str = "ubuntu:22.04"
    pod_name_prefix: str = "tryon-model-volume-sync"
    volume_mount_path: str = "/runpod-volume"
    vcpu_count: int = 2
    container_disk_gb: int = 10
    pod_ready_timeout_seconds: int = 900
    ssh_port_timeout_seconds: int = 360
    ssh_ready_timeout_seconds: int = 360
    transfer_timeout_seconds: int = 24 * 60 * 60
    poll_interval_seconds: int = 5

    @classmethod
    def load(cls) -> "RunPodModelVolumeSyncSettings":
        return cls(
            pod_image=os.getenv("RUNPOD_MODEL_SYNC_IMAGE", cls.pod_image),
            pod_name_prefix=os.getenv("RUNPOD_MODEL_SYNC_POD_PREFIX", cls.pod_name_prefix),
            volume_mount_path=os.getenv("RUNPOD_MODEL_SYNC_MOUNT_PATH", cls.volume_mount_path),
            vcpu_count=max(1, int(os.getenv("RUNPOD_MODEL_SYNC_VCPU", str(cls.vcpu_count)))),
            container_disk_gb=max(5, int(os.getenv("RUNPOD_MODEL_SYNC_DISK_GB", str(cls.container_disk_gb)))),
            pod_ready_timeout_seconds=max(60, int(os.getenv("RUNPOD_MODEL_SYNC_POD_TIMEOUT", str(cls.pod_ready_timeout_seconds)))),
            ssh_port_timeout_seconds=max(30, int(os.getenv("RUNPOD_MODEL_SYNC_SSH_PORT_TIMEOUT", str(cls.ssh_port_timeout_seconds)))),
            ssh_ready_timeout_seconds=max(60, int(os.getenv("RUNPOD_MODEL_SYNC_SSH_TIMEOUT", str(cls.ssh_ready_timeout_seconds)))),
            transfer_timeout_seconds=max(300, int(os.getenv("RUNPOD_MODEL_SYNC_TRANSFER_TIMEOUT", str(cls.transfer_timeout_seconds)))),
            poll_interval_seconds=max(2, int(os.getenv("RUNPOD_MODEL_SYNC_POLL_INTERVAL", str(cls.poll_interval_seconds)))),
        )


def resolve_private_key_path() -> Path:
    configured = str(os.getenv("RUNPOD_SSH_PRIVATE_KEY") or "").strip()
    if configured:
        path = Path(os.path.expandvars(os.path.expanduser(configured)))
    else:
        home = Path(os.getenv("USERPROFILE") or Path.home())
        dedicated = home / ".ssh" / "tryon_runpod_export"
        path = dedicated if dedicated.is_file() else home / ".ssh" / "id_ed25519"
    path = path.resolve()
    if not path.is_file():
        raise RuntimeError(
            "No se encontró la clave privada SSH de RunPod. Configura RUNPOD_SSH_PRIVATE_KEY "
            f"o crea la clave esperada en: {path}"
        )
    return path


def resolve_public_key_path(private_key: Path) -> Path:
    configured = str(os.getenv("RUNPOD_SSH_PUBLIC_KEY") or "").strip()
    if configured:
        path = Path(os.path.expandvars(os.path.expanduser(configured)))
    else:
        path = Path(str(private_key) + ".pub")
    path = path.resolve()
    if not path.is_file():
        raise RuntimeError(
            "No se encontró la clave pública asociada. Debe existir junto a la privada con extensión .pub "
            f"o configurarse RUNPOD_SSH_PUBLIC_KEY. Ruta esperada: {path}"
        )
    return path
