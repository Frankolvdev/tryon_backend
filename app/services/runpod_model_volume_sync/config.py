from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

try:
    from app.services.runpod_model_volume_sync.private_key_inline import (
        RUNPOD_SSH_PRIVATE_KEY_INLINE,
        RUNPOD_SSH_PUBLIC_KEY_INLINE,
    )
except ImportError:
    RUNPOD_SSH_PRIVATE_KEY_INLINE = ""
    RUNPOD_SSH_PUBLIC_KEY_INLINE = ""


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


def _materialize_inline_secret(value: str, *, suffix: str) -> Path:
    normalized = str(value or "").strip().replace("\r\n", "\n") + "\n"
    target = Path(tempfile.gettempdir()) / f"tryon-runpod-inline-{os.getpid()}{suffix}"
    target.write_text(normalized, encoding="utf-8", newline="\n")
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return target.resolve()


def resolve_private_key_path() -> Path:
    inline = str(RUNPOD_SSH_PRIVATE_KEY_INLINE or "").strip()
    if inline and "PEGA_AQUI_LA_CLAVE_PRIVADA_COMPLETA" not in inline:
        if "BEGIN OPENSSH PRIVATE KEY" not in inline:
            raise RuntimeError(
                "RUNPOD_SSH_PRIVATE_KEY_INLINE no contiene una clave privada OpenSSH válida."
            )
        return _materialize_inline_secret(inline, suffix=".key")

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
            "No se encontró la clave privada SSH de RunPod. Pega temporalmente la clave en "
            "app/services/runpod_model_volume_sync/private_key_inline.py, configura "
            "RUNPOD_SSH_PRIVATE_KEY o crea una clave SSH local."
        )
    return path


def resolve_public_key_path(private_key: Path) -> Path:
    inline = str(RUNPOD_SSH_PUBLIC_KEY_INLINE or "").strip()
    if inline and "PEGA_AQUI_LA_CLAVE_PUBLICA_COMPLETA" not in inline:
        if not inline.startswith(("ssh-", "ecdsa-")):
            raise RuntimeError(
                "RUNPOD_SSH_PUBLIC_KEY_INLINE no contiene una clave pública SSH válida."
            )
        return _materialize_inline_secret(inline, suffix=".pub")

    configured = str(os.getenv("RUNPOD_SSH_PUBLIC_KEY") or "").strip()
    if configured:
        path = Path(os.path.expandvars(os.path.expanduser(configured)))
    else:
        path = Path(str(private_key) + ".pub")
    path = path.resolve()
    if not path.is_file():
        raise RuntimeError(
            "No se encontró la clave pública asociada. Pégala temporalmente en "
            "app/services/runpod_model_volume_sync/private_key_inline.py o configura "
            f"RUNPOD_SSH_PUBLIC_KEY. Ruta esperada: {path}"
        )
    return path

