from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from app.services.runpod_control_plane_service import runpod_control_plane_service

ProgressCallback = Callable[[str, int, str], None]


@dataclass(frozen=True)
class RunPodSshTarget:
    pod_id: str
    host: str
    port: int


class RunPodVolumeSyncService:
    """Sincroniza un árbol local con un Network Volume mediante un Pod efímero.

    Límite de seguridad: esta clase solo elimina el Pod creado por ella. Nunca
    contiene ni llama operaciones de eliminación de Network Volumes.
    """

    POD_NAME_PREFIX = "tryon-model-sync"
    POD_IMAGE = "ubuntu:22.04"
    VOLUME_MOUNT_PATH = "/runpod-volume"
    CPU_FLAVORS = ["cpu3c", "cpu3g", "cpu3m", "cpu5c", "cpu5g", "cpu5m"]
    POD_READY_TIMEOUT_SECONDS = 900
    SSH_READY_TIMEOUT_SECONDS = 300
    COMMAND_TIMEOUT_SECONDS = 86400

    @classmethod
    def _private_key_path(cls) -> Path:
        configured = str(os.getenv("RUNPOD_SSH_PRIVATE_KEY") or "").strip()
        if configured:
            return Path(os.path.expandvars(os.path.expanduser(configured))).resolve()
        home = Path(os.getenv("USERPROFILE") or Path.home())
        return (home / ".ssh" / "id_ed25519").resolve()

    @staticmethod
    def _validate_remote_path(remote_path: str) -> str:
        normalized = str(remote_path or "").replace("\\", "/").strip("/")
        parts = PurePosixPath(normalized).parts if normalized else ()
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("La ruta remota de RunPod contiene segmentos no permitidos.")
        return "/".join(parts)

    @staticmethod
    def _run(command: list[str], *, timeout: int, capture: bool = True) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                command,
                check=True,
                text=True,
                capture_output=capture,
                timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"No se encontró el ejecutable requerido: {command[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"El comando excedió el tiempo máximo: {command[0]}") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            raise RuntimeError(f"Falló {command[0]}: {detail or f'código {exc.returncode}'}") from exc

    @classmethod
    def _wsl_path(cls, path: Path) -> str:
        """Convierte rutas Windows a WSL sin pasar backslashes por wslpath.

        Algunas combinaciones de Windows/WSL interpretan las barras invertidas
        como escapes y convierten, por ejemplo, C:\\Users\\frank en
        C:Usersfrank. La conversión directa evita ese problema.
        """
        raw = str(path.resolve())
        normalized = raw.replace("\\", "/")

        # Ruta local con letra de unidad: C:/Users/... -> /mnt/c/Users/...
        if len(normalized) >= 3 and normalized[1] == ":" and normalized[2] == "/":
            drive = normalized[0].lower()
            remainder = normalized[3:].lstrip("/")
            return f"/mnt/{drive}/{remainder}"

        # Si ya es una ruta POSIX/WSL, se conserva.
        if normalized.startswith("/"):
            return normalized

        # Las rutas UNC no tienen una traducción universal estable; se intenta
        # la conversión oficial pasando la ruta por stdin para no perder barras.
        try:
            completed = subprocess.run(
                ["wsl.exe", "bash", "-lc", "read -r p; wslpath -a -u -- \"$p\""],
                input=raw + "\n",
                check=True,
                text=True,
                capture_output=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise RuntimeError(f"WSL no pudo convertir la ruta: {raw}") from exc

        value = (completed.stdout or "").strip()
        if not value:
            raise RuntimeError(f"WSL no pudo convertir la ruta: {raw}")
        return value

    @classmethod
    def _transport(cls, source_root: Path, private_key: Path) -> tuple[str, str, str]:
        """Devuelve (modo, rsync, ssh). En Windows usa WSL como exige rsync."""
        if os.name == "nt":
            if not shutil.which("wsl.exe"):
                raise RuntimeError(
                    "rsync en Windows requiere WSL. Instala WSL y Ubuntu antes de exportar a RunPod."
                )
            probe = cls._run(
                ["wsl.exe", "bash", "-lc", "command -v rsync && command -v ssh"],
                timeout=30,
            )
            if len([line for line in (probe.stdout or "").splitlines() if line.strip()]) < 2:
                raise RuntimeError(
                    "WSL está disponible, pero faltan rsync u openssh-client. Ejecuta en WSL: "
                    "sudo apt update && sudo apt install -y rsync openssh-client"
                )
            return "wsl", cls._wsl_path(source_root), cls._wsl_path(private_key)

        if not shutil.which("rsync") or not shutil.which("ssh"):
            raise RuntimeError("El backend necesita rsync y OpenSSH instalados para exportar a RunPod.")
        return "native", str(source_root), str(private_key)

    @staticmethod
    def _startup_command() -> list[str]:
        script = r"""
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends openssh-server openssh-client rsync ca-certificates python3
mkdir -p /run/sshd /root/.ssh
chmod 700 /root/.ssh
if [ -n "${PUBLIC_KEY:-}" ]; then
  printf '%s\n' "$PUBLIC_KEY" > /root/.ssh/authorized_keys
fi
chmod 600 /root/.ssh/authorized_keys
printf '%s\n' 'PermitRootLogin prohibit-password' 'PasswordAuthentication no' 'PubkeyAuthentication yes' > /etc/ssh/sshd_config.d/99-runpod-sync.conf
exec /usr/sbin/sshd -D -e
""".strip()
        return ["bash", "-lc", script]

    @classmethod
    def _create_pod(cls, *, api_key: str, volume_id: str, data_center_id: str, timeout_seconds: int) -> dict[str, Any]:
        payload = {
            "name": f"{cls.POD_NAME_PREFIX}-{int(time.time())}",
            "computeType": "CPU",
            "cloudType": "SECURE",
            "cpuFlavorIds": cls.CPU_FLAVORS,
            "cpuFlavorPriority": "availability",
            "vcpuCount": 2,
            "containerDiskInGb": 20,
            "imageName": cls.POD_IMAGE,
            "dockerEntrypoint": [],
            "dockerStartCmd": cls._startup_command(),
            "interruptible": False,
            "locked": False,
            "dataCenterIds": [data_center_id],
            "dataCenterPriority": "custom",
            "networkVolumeId": volume_id,
            "volumeInGb": 0,
            "volumeMountPath": cls.VOLUME_MOUNT_PATH,
            "ports": ["22/tcp"],
            "supportPublicIp": True,
        }
        return runpod_control_plane_service.create_pod(
            api_key=api_key,
            payload=payload,
            timeout_seconds=timeout_seconds,
        )

    @classmethod
    def _wait_for_ssh_target(cls, *, api_key: str, pod_id: str, timeout_seconds: int, notify: ProgressCallback) -> RunPodSshTarget:
        deadline = time.monotonic() + timeout_seconds
        last_status = "inicializando"
        while time.monotonic() < deadline:
            pod = runpod_control_plane_service.get_pod(
                pod_id,
                api_key=api_key,
                timeout_seconds=60,
            )
            host = str(pod.get("publicIp") or "").strip()
            mappings = pod.get("portMappings") or {}
            port_value = mappings.get("22") or mappings.get(22)
            status = str(pod.get("desiredStatus") or pod.get("status") or pod.get("lastStatusChange") or "").strip()
            if status and status != last_status:
                last_status = status
                notify("runpod-pod-starting", 95, f"Pod temporal: {status}")
            if host and port_value:
                return RunPodSshTarget(pod_id=pod_id, host=host, port=int(port_value))
            time.sleep(5)
        raise RuntimeError("RunPod no asignó IP pública y puerto SSH al Pod temporal dentro del tiempo esperado.")

    @classmethod
    def _ssh_base(cls, *, mode: str, key_path: str, target: RunPodSshTarget) -> list[str]:
        options = [
            "-i", key_path,
            "-p", str(target.port),
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=15",
            "-o", "ServerAliveInterval=20",
            "-o", "ServerAliveCountMax=6",
        ]
        if mode == "wsl":
            return ["wsl.exe", "ssh", *options, f"root@{target.host}"]
        return ["ssh", *options, f"root@{target.host}"]

    @classmethod
    def _wait_for_ssh(cls, *, mode: str, key_path: str, target: RunPodSshTarget, notify: ProgressCallback) -> None:
        deadline = time.monotonic() + cls.SSH_READY_TIMEOUT_SECONDS
        last_error = ""
        while time.monotonic() < deadline:
            command = cls._ssh_base(mode=mode, key_path=key_path, target=target) + ["true"]
            try:
                cls._run(command, timeout=30)
                notify("runpod-ssh-ready", 96, "SSH del Pod temporal está listo.")
                return
            except RuntimeError as exc:
                last_error = str(exc)
                time.sleep(5)
        raise RuntimeError(f"No fue posible conectar por SSH al Pod temporal: {last_error}")

    @classmethod
    def _remote_manifest(cls, models_root: Path) -> dict[str, int]:
        return {
            item.relative_to(models_root).as_posix(): item.stat().st_size
            for item in sorted(models_root.rglob("*"))
            if item.is_file()
        }

    @classmethod
    def _sync(
        cls,
        *,
        mode: str,
        source_path: str,
        key_path: str,
        target: RunPodSshTarget,
        destination: str,
        overwrite: bool,
        notify: ProgressCallback,
    ) -> None:
        ssh_transport = (
            f"ssh -i {shlex.quote(key_path)} -p {target.port} "
            "-o BatchMode=yes -o StrictHostKeyChecking=accept-new "
            "-o ServerAliveInterval=20 -o ServerAliveCountMax=6"
        )
        source = source_path.rstrip("/") + "/"
        destination_uri = f"root@{target.host}:{destination.rstrip('/')}/"
        flags = [
            "-a",
            "--partial",
            "--partial-dir=.rsync-partial",
            "--info=progress2,stats2",
            "--human-readable",
            "--protect-args",
        ]
        if not overwrite:
            flags.extend(["--ignore-existing"])
        if mode == "wsl":
            command = ["wsl.exe", "rsync", *flags, "-e", ssh_transport, source, destination_uri]
        else:
            command = ["rsync", *flags, "-e", ssh_transport, source, destination_uri]
        notify("runpod-rsync", 97, "Sincronizando modelos por rsync…")
        cls._run(command, timeout=cls.COMMAND_TIMEOUT_SECONDS)

    @classmethod
    def _verify(
        cls,
        *,
        mode: str,
        key_path: str,
        target: RunPodSshTarget,
        destination: str,
        local_manifest: dict[str, int],
        notify: ProgressCallback,
    ) -> None:
        manifest_json = json.dumps(local_manifest, ensure_ascii=False, separators=(",", ":"))
        python_script = (
            "import json,os,sys; root=sys.argv[1]; expected=json.loads(sys.stdin.read()); "
            "bad=[]; "
            "[(bad.append((p,s,os.path.getsize(os.path.join(root,p)) if os.path.isfile(os.path.join(root,p)) else -1))) "
            "for p,s in expected.items() if (not os.path.isfile(os.path.join(root,p)) or os.path.getsize(os.path.join(root,p))!=s)]; "
            "print(json.dumps(bad)); sys.exit(1 if bad else 0)"
        )
        remote = f"python3 -c {shlex.quote(python_script)} {shlex.quote(destination)}"
        command = cls._ssh_base(mode=mode, key_path=key_path, target=target) + [remote]
        notify("runpod-verifying", 98, "Verificando archivos y tamaños en el Network Volume…")
        try:
            subprocess.run(
                command,
                input=manifest_json,
                check=True,
                text=True,
                capture_output=True,
                timeout=cls.COMMAND_TIMEOUT_SECONDS,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stdout or exc.stderr or "").strip()
            raise RuntimeError(f"La verificación del Network Volume falló: {detail}") from exc

    @classmethod
    def sync_tree(
        cls,
        *,
        api_key: str,
        volume_id: str,
        data_center_id: str,
        models_root: Path,
        remote_path: str,
        overwrite: bool,
        timeout_seconds: int,
        notify: ProgressCallback,
    ) -> dict[str, Any]:
        if not api_key.strip() or not volume_id.strip() or not data_center_id.strip():
            raise ValueError("Configura API Key, Network Volume ID y Data Center ID de RunPod.")
        if not models_root.is_dir():
            raise ValueError(f"No existe la carpeta local de modelos: {models_root}")

        key_path = cls._private_key_path()
        if not key_path.is_file():
            raise ValueError(f"No se encontró la clave privada SSH de RunPod en: {key_path}")
        remote_suffix = cls._validate_remote_path(remote_path)
        destination = cls.VOLUME_MOUNT_PATH + (f"/{remote_suffix}" if remote_suffix else "")
        mode, source_path, transport_key = cls._transport(models_root, key_path)
        manifest = cls._remote_manifest(models_root)
        pod_id: str | None = None
        cleanup_error: str | None = None
        started = time.monotonic()

        try:
            notify("runpod-pod-creating", 94, "Creando Pod temporal económico para sincronizar el volumen…")
            pod = cls._create_pod(
                api_key=api_key.strip(),
                volume_id=volume_id.strip(),
                data_center_id=data_center_id.strip().upper(),
                timeout_seconds=min(max(timeout_seconds, 60), 900),
            )
            pod_id = str(pod.get("id") or "").strip()
            if not pod_id:
                raise RuntimeError(f"RunPod creó el Pod temporal sin devolver un ID: {pod!r}")

            target = cls._wait_for_ssh_target(
                api_key=api_key.strip(),
                pod_id=pod_id,
                timeout_seconds=min(max(timeout_seconds, 60), cls.POD_READY_TIMEOUT_SECONDS),
                notify=notify,
            )
            cls._wait_for_ssh(mode=mode, key_path=transport_key, target=target, notify=notify)

            mkdir_command = cls._ssh_base(mode=mode, key_path=transport_key, target=target) + [
                f"mkdir -p -- {shlex.quote(destination)}"
            ]
            cls._run(mkdir_command, timeout=60)
            cls._sync(
                mode=mode,
                source_path=source_path,
                key_path=transport_key,
                target=target,
                destination=destination,
                overwrite=overwrite,
                notify=notify,
            )
            cls._verify(
                mode=mode,
                key_path=transport_key,
                target=target,
                destination=destination,
                local_manifest=manifest,
                notify=notify,
            )
            return {
                "type": "runpod_network_volume",
                "transport": "ssh+rsync",
                "volume_id": volume_id.strip(),
                "data_center_id": data_center_id.strip().upper(),
                "path": destination,
                "files_verified": len(manifest),
                "bytes_verified": sum(manifest.values()),
                "temporary_pod_id": pod_id,
                "elapsed_seconds": round(time.monotonic() - started, 3),
            }
        finally:
            if pod_id:
                try:
                    notify("runpod-pod-cleanup", 99, "Eliminando únicamente el Pod temporal…")
                    runpod_control_plane_service.delete_pod(
                        pod_id,
                        api_key=api_key.strip(),
                        timeout_seconds=60,
                    )
                except Exception as exc:  # conservar el error principal si existe
                    cleanup_error = str(exc)
            if cleanup_error:
                import sys
                if sys.exc_info()[0] is None:
                    raise RuntimeError(
                        "La sincronización terminó, pero RunPod no permitió eliminar el Pod temporal "
                        f"{pod_id}. El Network Volume no fue modificado ni eliminado. Error: {cleanup_error}"
                    )
