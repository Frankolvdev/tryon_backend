from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ProgressCallback = Callable[[str, int, str], None]


@dataclass(frozen=True)
class SshTarget:
    host: str
    port: int


class RsyncSshTransport:
    """Local SSH/rsync adapter. Windows is supported through WSL."""

    def __init__(self, private_key: Path) -> None:
        self.private_key = private_key
        self.mode = "wsl" if os.name == "nt" else "native"
        self._wsl_key_path: str | None = None
        self._validate_tools()
        if self.mode == "wsl":
            source = self.path(self.private_key)
            target = f"/tmp/tryon-runpod-key-{os.getpid()}-{int(time.time() * 1000)}"
            command = f"install -m 600 -- {shlex.quote(source)} {shlex.quote(target)}"
            self._run(["wsl.exe", "bash", "-lc", command], timeout=30)
            self._wsl_key_path = target

    @staticmethod
    def _creation_flags() -> int:
        return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

    def _run(self, command: list[str], *, timeout: int, check: bool = True) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                command,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=check,
                creationflags=self._creation_flags(),
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"No se encontró el ejecutable requerido: {command[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"El comando excedió el tiempo máximo: {command[0]}") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            raise RuntimeError(f"Falló {command[0]}: {detail or f'código {exc.returncode}'}") from exc

    def _validate_tools(self) -> None:
        if self.mode == "wsl":
            if not shutil.which("wsl.exe"):
                raise RuntimeError("La exportación RunPod con rsync requiere WSL en Windows.")
            probe = self._run(
                ["wsl.exe", "bash", "-lc", "command -v rsync >/dev/null && command -v ssh >/dev/null"],
                timeout=30,
                check=False,
            )
            if probe.returncode != 0:
                raise RuntimeError(
                    "Faltan rsync u openssh-client dentro de WSL. Ejecuta: "
                    "sudo apt update && sudo apt install -y rsync openssh-client"
                )
        elif not shutil.which("rsync") or not shutil.which("ssh"):
            raise RuntimeError("El backend necesita rsync y OpenSSH para exportar modelos a RunPod.")

    def path(self, local_path: Path) -> str:
        """Convierte una ruta local a una ruta utilizable dentro de WSL.

        No invoca ``wslpath`` con una ruta de Windows como argumento directo porque
        algunas combinaciones de Windows/WSL eliminan las barras invertidas antes de
        que ``wslpath`` las reciba (por ejemplo, ``C:\\Users`` termina como
        ``C:Users``). La conversión de rutas con letra de unidad es determinista.
        """
        raw = str(local_path)
        if self.mode == "native":
            return raw

        drive_match = re.match(r"^([A-Za-z]):[\\/](.*)$", raw)
        if drive_match:
            drive = drive_match.group(1).lower()
            remainder = drive_match.group(2).replace("\\", "/")
            return f"/mnt/{drive}/{remainder}"

        # Una ruta que ya usa sintaxis Linux/WSL no necesita conversión.
        if raw.startswith("/"):
            return raw

        raise RuntimeError(
            "No fue posible convertir la ruta local a WSL. "
            f"Usa una ruta absoluta de Windows, por ejemplo C:\\Users\\usuario\\.ssh\\id_ed25519. Ruta recibida: {raw}"
        )

    def public_key(self) -> str:
        pub = self.private_key.with_suffix(self.private_key.suffix + ".pub")
        if pub.is_file():
            value = pub.read_text(encoding="utf-8").strip()
        else:
            key = self.path(self.private_key)
            command = ["wsl.exe", "ssh-keygen", "-y", "-f", key] if self.mode == "wsl" else ["ssh-keygen", "-y", "-f", key]
            value = (self._run(command, timeout=30).stdout or "").strip()
        if not value.startswith(("ssh-ed25519 ", "ssh-rsa ", "ecdsa-sha2-")):
            raise RuntimeError("No fue posible obtener una clave pública SSH válida.")
        return value

    def close(self) -> None:
        if self.mode == "wsl" and self._wsl_key_path:
            self._run(
                ["wsl.exe", "bash", "-lc", f"rm -f -- {shlex.quote(self._wsl_key_path)}"],
                timeout=30,
                check=False,
            )
            self._wsl_key_path = None

    def ssh_options(self, target: SshTarget) -> list[str]:
        key_path = self._wsl_key_path if self.mode == "wsl" else str(self.private_key)
        if not key_path:
            raise RuntimeError("La copia segura de la clave SSH no está disponible.")
        return [
            "-i", key_path,
            "-p", str(target.port),
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=15",
            "-o", "ServerAliveInterval=20",
            "-o", "ServerAliveCountMax=6",
        ]

    def ssh(self, target: SshTarget, remote_command: str, *, timeout: int, check: bool = True) -> subprocess.CompletedProcess[str]:
        command = ["ssh", *self.ssh_options(target), f"root@{target.host}", remote_command]
        if self.mode == "wsl":
            command.insert(0, "wsl.exe")
        return self._run(command, timeout=timeout, check=check)

    def wait_until_ready(self, target: SshTarget, *, timeout: int, poll_interval: int,
                         notify: ProgressCallback) -> None:
        deadline = time.monotonic() + timeout
        last_error = ""
        while time.monotonic() < deadline:
            result = self.ssh(target, "true", timeout=30, check=False)
            if result.returncode == 0:
                notify("runpod-ssh-ready", 96, "SSH del Pod temporal está listo.")
                return
            last_error = (result.stderr or result.stdout or "SSH aún no disponible").strip()[-1000:]
            time.sleep(poll_interval)
        raise RuntimeError(f"No fue posible conectar por SSH al Pod temporal: {last_error}")

    def rsync(self, source_root: Path, target: SshTarget, remote_dir: str, *, overwrite: bool,
              timeout: int, notify: ProgressCallback) -> str:
        source = self.path(source_root).rstrip("/") + "/"
        ssh_transport = "ssh " + " ".join(shlex.quote(part) for part in self.ssh_options(target))
        flags = [
            "-a", "--human-readable", "--info=progress2,stats2", "--partial",
            "--partial-dir=.rsync-partial", "--delay-updates", "--protect-args",
        ]
        if not overwrite:
            flags.append("--ignore-existing")
        destination = f"root@{target.host}:{remote_dir.rstrip('/')}/"
        command = ["rsync", *flags, "-e", ssh_transport, source, destination]
        if self.mode == "wsl":
            command.insert(0, "wsl.exe")

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=self._creation_flags(),
        )
        output: list[str] = []
        percent_re = re.compile(r"\b(\d{1,3})%\b")
        started = time.monotonic()
        assert process.stdout is not None
        try:
            for line in process.stdout:
                clean = line.strip()
                if clean:
                    output.append(clean)
                    match = percent_re.search(clean)
                    pct = min(100, int(match.group(1))) if match else None
                    ui_pct = 96 + min(2, int((pct or 0) * 2 / 100))
                    notify("runpod-rsync", ui_pct, f"Sincronizando por rsync: {clean[-500:]}")
                if time.monotonic() - started > timeout:
                    process.kill()
                    raise RuntimeError("La sincronización rsync excedió el tiempo máximo configurado.")
            code = process.wait(timeout=30)
        finally:
            if process.poll() is None:
                process.kill()
        if code != 0:
            raise RuntimeError(f"rsync terminó con código {code}: {' | '.join(output[-20:])}")
        return "\n".join(output[-100:])
