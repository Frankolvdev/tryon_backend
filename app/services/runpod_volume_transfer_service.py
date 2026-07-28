from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import subprocess
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from app.services.runpod_control_plane_service import RunPodControlPlaneService

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[str, int, str], None]


class RunPodVolumeTransferService:
    """Copia modelos a un Network Volume mediante un Pod temporal.

    El Network Volume nunca se crea, desmonta ni elimina aquí. El único recurso
    efímero administrado por este servicio es el Pod de transferencia.
    """

    IMAGE = os.getenv(
        "RUNPOD_VOLUME_TRANSFER_IMAGE",
        "runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04",
    )
    MOUNT_PATH = "/runpod-volume"

    def __init__(self, control_plane: RunPodControlPlaneService | None = None) -> None:
        self.control_plane = control_plane or RunPodControlPlaneService()

    @staticmethod
    def _human_bytes(value: float) -> str:
        units = ("B", "KB", "MB", "GB", "TB")
        size = float(max(0, value))
        for unit in units:
            if size < 1024 or unit == units[-1]:
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024
        return f"{size:.1f} TB"

    @staticmethod
    def _private_key_path() -> Path:
        configured = str(os.getenv("RUNPOD_SSH_PRIVATE_KEY") or "").strip()
        candidates = [
            Path(configured).expanduser() if configured else None,
            Path.home() / ".ssh" / "id_ed25519",
            Path.home() / ".ssh" / "id_rsa",
        ]
        for candidate in candidates:
            if candidate and candidate.is_file():
                return candidate.resolve()
        raise RuntimeError(
            "No se encontró una clave SSH privada para el Pod temporal. "
            "Configura RUNPOD_SSH_PRIVATE_KEY o crea ~/.ssh/id_ed25519 y agrega "
            "su clave pública a tu cuenta de RunPod."
        )

    @staticmethod
    def _public_key(private_key: Path) -> str:
        sibling = Path(str(private_key) + ".pub")
        if sibling.is_file():
            value = sibling.read_text(encoding="utf-8").strip()
            if value:
                return value
        ssh_keygen = shutil.which("ssh-keygen")
        if not ssh_keygen:
            raise RuntimeError(
                f"No existe {sibling} y ssh-keygen no está disponible para derivar la clave pública."
            )
        completed = subprocess.run(
            [ssh_keygen, "-y", "-f", str(private_key)],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode != 0 or not completed.stdout.strip():
            detail = (completed.stderr or completed.stdout or "error desconocido").strip()
            raise RuntimeError(f"No se pudo derivar la clave SSH pública: {detail}")
        return completed.stdout.strip()

    @staticmethod
    def _ssh_base(ip: str, port: int, private_key: Path) -> list[str]:
        ssh = shutil.which("ssh")
        if not ssh:
            raise RuntimeError("OpenSSH (ssh) no está disponible en el servidor donde corre el backend.")
        return [
            ssh,
            "-i", str(private_key),
            "-p", str(port),
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=15",
            "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=4",
            f"root@{ip}",
        ]

    @staticmethod
    def _scp_base(ip: str, port: int, private_key: Path) -> list[str]:
        scp = shutil.which("scp")
        if not scp:
            raise RuntimeError("OpenSSH (scp) no está disponible en el servidor donde corre el backend.")
        return [
            scp,
            "-i", str(private_key),
            "-P", str(port),
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=15",
        ]

    @staticmethod
    def _run(command: list[str], *, timeout: int, error_prefix: str) -> str:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout)),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
        if completed.returncode != 0:
            raise RuntimeError(f"{error_prefix}: {output[-5000:] or 'sin detalle'}")
        return output

    def _wait_ready(
        self,
        *,
        pod_id: str,
        api_key: str,
        private_key: Path,
        timeout_seconds: int,
        notify: ProgressCallback,
    ) -> tuple[str, int, dict[str, Any]]:
        deadline = time.monotonic() + max(60, timeout_seconds)
        last_state = ""
        while time.monotonic() < deadline:
            pod = self.control_plane.get_pod(pod_id, api_key=api_key, timeout_seconds=30)
            state = str(pod.get("desiredStatus") or pod.get("status") or "INICIALIZANDO")
            if state != last_state:
                notify("runpod-pod-wait", 95, f"Pod temporal {pod_id}: {state}…")
                last_state = state
            ip = str(pod.get("publicIp") or "").strip()
            mappings = pod.get("portMappings") or {}
            port_raw = mappings.get("22") if isinstance(mappings, dict) else None
            if ip and port_raw:
                try:
                    port = int(port_raw)
                except (TypeError, ValueError):
                    port = 0
                if port:
                    try:
                        self._run(
                            self._ssh_base(ip, port, private_key) + ["printf READY"],
                            timeout=20,
                            error_prefix="SSH del Pod temporal todavía no está listo",
                        )
                        return ip, port, pod
                    except Exception:
                        pass
            time.sleep(5)
        raise TimeoutError(f"El Pod temporal {pod_id} no quedó accesible por SSH dentro del tiempo permitido.")

    def transfer(
        self,
        *,
        api_key: str,
        volume_id: str,
        data_center_id: str,
        gpu_type_ids: list[str],
        allowed_cuda_versions: list[str],
        container_disk_gb: int,
        timeout_seconds: int,
        models_root: Path,
        remote_path: str,
        overwrite: bool,
        notify: ProgressCallback,
    ) -> dict[str, Any]:
        api_key = str(api_key or "").strip()
        volume_id = str(volume_id or "").strip()
        data_center_id = str(data_center_id or "").strip().upper()
        if not api_key:
            raise ValueError("Configura la API key normal de RunPod antes de exportar.")
        if not volume_id:
            raise ValueError("Configura el Network Volume ID de RunPod antes de exportar.")
        if not data_center_id:
            raise ValueError("Configura el Data Center ID de RunPod antes de exportar.")

        private_key = self._private_key_path()
        public_key = self._public_key(private_key)
        files = sorted(
            [item for item in models_root.rglob("*") if item.is_file()],
            key=lambda item: item.relative_to(models_root).as_posix().casefold(),
        )
        total_bytes = sum(item.stat().st_size for item in files)
        transferred_bytes = 0
        uploaded = 0
        skipped = 0
        pod_id: str | None = None
        cleanup_error: str | None = None
        started = time.monotonic()
        suffix = uuid.uuid4().hex[:10]
        pod_name = f"tryon-model-export-{suffix}"

        # El comando mantiene vivo el Pod y garantiza sshd + herramientas de
        # validación. PUBLIC_KEY se inyecta solamente al Pod temporal.
        start_command = (
            "set -e; "
            "command -v sshd >/dev/null 2>&1 || (apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server); "
            "mkdir -p /run/sshd /root/.ssh; chmod 700 /root/.ssh; "
            "printf \"%s\\n\" \"$SSH_PUBLIC_KEY\" > /root/.ssh/authorized_keys; chmod 600 /root/.ssh/authorized_keys; "
            "/usr/sbin/sshd; sleep infinity"
        )

        try:
            notify("runpod-pod-create", 94, f"Creando Pod temporal en {data_center_id}…")
            pod = self.control_plane.create_pod(
                api_key=api_key,
                payload={
                    "name": pod_name,
                    "imageName": self.IMAGE,
                    "computeType": "GPU",
                    "cloudType": "SECURE",
                    "gpuCount": 1,
                    "gpuTypeIds": list(gpu_type_ids or ["NVIDIA L40S"]),
                    "gpuTypePriority": "availability",
                    "allowedCudaVersions": list(allowed_cuda_versions or []),
                    "dataCenterIds": [data_center_id],
                    "dataCenterPriority": "availability",
                    "containerDiskInGb": max(20, int(container_disk_gb or 20)),
                    "networkVolumeId": volume_id,
                    "volumeMountPath": self.MOUNT_PATH,
                    "ports": ["22/tcp"],
                    "supportPublicIp": True,
                    "env": {"SSH_PUBLIC_KEY": public_key},
                    "dockerEntrypoint": [],
                    "dockerStartCmd": ["bash", "-lc", start_command],
                    "interruptible": False,
                },
                timeout_seconds=60,
            )
            pod_id = str(pod.get("id") or "").strip()
            if not pod_id:
                raise RuntimeError(f"RunPod creó una respuesta sin ID de Pod: {json.dumps(pod)[:2000]}")

            ip, port, pod = self._wait_ready(
                pod_id=pod_id,
                api_key=api_key,
                private_key=private_key,
                timeout_seconds=min(max(180, timeout_seconds), 1800),
                notify=notify,
            )
            ssh_base = self._ssh_base(ip, port, private_key)
            scp_base = self._scp_base(ip, port, private_key)
            target_root = PurePosixPath(self.MOUNT_PATH)
            if remote_path.strip("/\\"):
                target_root /= PurePosixPath(remote_path.replace("\\", "/").strip("/"))

            self._run(
                ssh_base + [f"mkdir -p {shlex.quote(str(target_root))}"],
                timeout=60,
                error_prefix="No se pudo preparar el directorio destino en el Network Volume",
            )

            for index, source in enumerate(files, start=1):
                relative = PurePosixPath(source.relative_to(models_root).as_posix())
                final_path = target_root / relative
                temp_path = final_path.with_name(final_path.name + f".tryon-upload-{suffix}")
                size = source.stat().st_size
                parent = final_path.parent

                # Consulta directa al filesystem montado. Si overwrite=False,
                # un archivo del mismo tamaño se considera ya sincronizado.
                probe = (
                    f"if [ -f {shlex.quote(str(final_path))} ]; then "
                    f"stat -c %s {shlex.quote(str(final_path))}; else printf MISSING; fi"
                )
                existing = self._run(ssh_base + [probe], timeout=30, error_prefix=f"No se pudo comprobar {relative}").strip().splitlines()[-1]
                if not overwrite and existing == str(size):
                    skipped += 1
                    transferred_bytes += size
                    notify(
                        "runpod-copy",
                        95 + min(3, int(3 * transferred_bytes / max(1, total_bytes))),
                        f"Omitido {index}/{len(files)}: {relative} (mismo tamaño).",
                    )
                    continue
                if not overwrite and existing != "MISSING":
                    skipped += 1
                    transferred_bytes += size
                    notify(
                        "runpod-copy",
                        95 + min(3, int(3 * transferred_bytes / max(1, total_bytes))),
                        f"Omitido {index}/{len(files)}: {relative} (ya existe y sobrescribir está desactivado).",
                    )
                    continue

                self._run(
                    ssh_base + [f"mkdir -p {shlex.quote(str(parent))}; rm -f {shlex.quote(str(temp_path))}"],
                    timeout=60,
                    error_prefix=f"No se pudo preparar la subida de {relative}",
                )
                notify(
                    "runpod-copy",
                    95 + min(3, int(3 * transferred_bytes / max(1, total_bytes))),
                    f"Transfiriendo {index}/{len(files)}: {relative} ({self._human_bytes(size)})…",
                )
                file_started = time.monotonic()
                command = scp_base + [str(source), f"root@{ip}:{shlex.quote(str(temp_path))}"]
                self._run(
                    command,
                    timeout=max(300, int(timeout_seconds)),
                    error_prefix=f"SCP no pudo transferir {relative}",
                )
                verify_and_commit = (
                    f"actual=$(stat -c %s {shlex.quote(str(temp_path))}); "
                    f"[ \"$actual\" = \"{size}\" ] || {{ echo SIZE_MISMATCH:$actual; exit 42; }}; "
                    f"mv -f {shlex.quote(str(temp_path))} {shlex.quote(str(final_path))}; "
                    f"sync; stat -c %s {shlex.quote(str(final_path))}"
                )
                confirmed = self._run(
                    ssh_base + [verify_and_commit],
                    timeout=120,
                    error_prefix=f"RunPod no pudo verificar/confirmar {relative}",
                ).strip().splitlines()[-1]
                if confirmed != str(size):
                    raise RuntimeError(
                        f"Tamaño remoto incorrecto para {relative}: local={size}, remoto={confirmed}."
                    )
                uploaded += 1
                transferred_bytes += size
                elapsed = max(0.001, time.monotonic() - file_started)
                notify(
                    "runpod-copy",
                    95 + min(3, int(3 * transferred_bytes / max(1, total_bytes))),
                    f"Completado {index}/{len(files)}: {relative} ({self._human_bytes(size / elapsed)}/s).",
                )

            return {
                "volume_id": volume_id,
                "data_center_id": data_center_id,
                "path": remote_path,
                "files_total": len(files),
                "files_uploaded": uploaded,
                "files_skipped": skipped,
                "bytes_total": total_bytes,
                "bytes_processed": transferred_bytes,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "transport": "temporary-pod-scp",
                "temporary_pod_id": pod_id,
                "temporary_pod_deleted": True,
            }
        finally:
            if pod_id:
                notify("runpod-pod-delete", 98, f"Eliminando únicamente el Pod temporal {pod_id}…")
                try:
                    self.control_plane.delete_pod(pod_id, api_key=api_key, timeout_seconds=60)
                except Exception as exc:  # no oculta el resultado/error principal
                    cleanup_error = str(exc)
                    logger.exception("No se pudo eliminar el Pod temporal %s", pod_id)
                    # Un Pod huérfano genera costo: el fallo de limpieza debe ser
                    # visible y no puede marcarse silenciosamente como éxito.
                    raise RuntimeError(
                        f"La transferencia terminó, pero no fue posible eliminar el Pod temporal {pod_id}: {exc}. "
                        "El Network Volume NO fue eliminado. Elimina manualmente solo ese Pod para detener cargos."
                    ) from exc


runpod_volume_transfer_service = RunPodVolumeTransferService()
