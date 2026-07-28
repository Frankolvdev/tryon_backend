from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ProgressCallback = Callable[[str, int, str], None]


@dataclass(frozen=True)
class SshTarget:
    host: str
    port: int


class RsyncSshTransport:
    """SSH/rsync adapter isolated to RunPod model-volume export.

    On Windows, commands run inside WSL. The private key is copied into WSL's
    Linux filesystem with mode 0600 and the public key is always derived from
    that exact copied private key. This prevents mismatched .pub files and
    avoids wslpath/mktemp/shell-quoting problems.
    """

    def __init__(self, private_key: Path) -> None:
        self.private_key = private_key
        self.mode = "wsl" if os.name == "nt" else "native"
        self._wsl_key_path: str | None = None
        self._validate_tools()
        if self.mode == "wsl":
            self._copy_private_key_to_wsl()
        self._public_key = self._derive_public_key()

    @staticmethod
    def _creation_flags() -> int:
        return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

    def _run(
        self,
        command: list[str],
        *,
        timeout: int,
        check: bool = True,
        stdin_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                command,
                input=stdin_text,
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
                ["wsl.exe", "bash", "-lc", "command -v rsync >/dev/null && command -v ssh >/dev/null && command -v ssh-keygen >/dev/null"],
                timeout=30,
                check=False,
            )
            if probe.returncode != 0:
                raise RuntimeError(
                    "Faltan rsync u OpenSSH dentro de WSL. Ejecuta: "
                    "sudo apt update && sudo apt install -y rsync openssh-client"
                )
        elif not all(shutil.which(name) for name in ("rsync", "ssh", "ssh-keygen")):
            raise RuntimeError("El backend necesita rsync y OpenSSH para exportar modelos a RunPod.")

    def _copy_private_key_to_wsl(self) -> str:
        try:
            key_text = self.private_key.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise RuntimeError(f"No fue posible leer la clave privada SSH: {self.private_key}") from exc
        if "PRIVATE KEY" not in key_text:
            raise RuntimeError(f"El archivo configurado no parece una clave privada SSH válida: {self.private_key}")

        target = f"/tmp/tryon-runpod-key-{os.getpid()}-{uuid.uuid4().hex}"
        # The target is generated internally and contains only safe characters.
        script = f"umask 077; cat > {target}; chmod 600 {target}; test -s {target}"
        self._run(["wsl.exe", "bash", "-lc", script], timeout=30, stdin_text=key_text)
        probe = self._run(["wsl.exe", "bash", "-lc", f"stat -c '%a %s' {target}"], timeout=15)
        detail = (probe.stdout or "").strip()
        if not detail.startswith("600 "):
            self._run(["wsl.exe", "bash", "-lc", f"rm -f {target}"], timeout=15, check=False)
            raise RuntimeError(f"WSL no creó correctamente la copia segura de la clave SSH: {detail or 'sin detalle'}")
        self._wsl_key_path = target
        return target

    def _key_path(self) -> str:
        if self.mode == "native":
            return str(self.private_key)
        if not self._wsl_key_path:
            return self._copy_private_key_to_wsl()
        probe = self._run(["wsl.exe", "bash", "-lc", f"test -s {self._wsl_key_path}"], timeout=15, check=False)
        if probe.returncode != 0:
            return self._copy_private_key_to_wsl()
        return self._wsl_key_path

    def _derive_public_key(self) -> str:
        key_path = self._key_path()
        command = ["ssh-keygen", "-y", "-f", key_path]
        if self.mode == "wsl":
            command.insert(0, "wsl.exe")
        result = self._run(command, timeout=30, check=False)
        value = (result.stdout or "").strip()
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            if "passphrase" in detail.lower() or "incorrect passphrase" in detail.lower():
                raise RuntimeError(
                    "La clave privada SSH tiene contraseña. Para esta exportación automática usa una clave sin passphrase."
                )
            raise RuntimeError(f"No fue posible derivar la clave pública desde la clave privada: {detail[-1500:]}")
        if not value.startswith(("ssh-ed25519 ", "ssh-rsa ", "ecdsa-sha2-")):
            raise RuntimeError("La clave pública derivada no tiene un formato SSH compatible.")
        # ssh-keygen -y normally returns type + base64. Strip comments defensively.
        parts = value.split()
        return " ".join(parts[:2])

    def public_key(self) -> str:
        return self._public_key

    def close(self) -> None:
        if self.mode == "wsl" and self._wsl_key_path:
            self._run(["wsl.exe", "bash", "-lc", f"rm -f {self._wsl_key_path}"], timeout=30, check=False)
            self._wsl_key_path = None

    def path(self, local_path: Path) -> str:
        raw = str(local_path)
        if self.mode == "native":
            return raw
        match = re.match(r"^([A-Za-z]):[\\/](.*)$", raw)
        if match:
            return f"/mnt/{match.group(1).lower()}/{match.group(2).replace(chr(92), '/')}"
        if raw.startswith("/"):
            return raw
        raise RuntimeError(f"No fue posible convertir la ruta local a WSL: {raw}")

    def ssh_options(self, target: SshTarget, *, verbose: bool = False) -> list[str]:
        options = [
            "-i", self._key_path(),
            "-p", str(target.port),
            "-o", "IdentitiesOnly=yes",
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "UserKnownHostsFile=/tmp/tryon-runpod-known-hosts",
            "-o", "ConnectTimeout=15",
            "-o", "ConnectionAttempts=1",
            "-o", "ServerAliveInterval=20",
            "-o", "ServerAliveCountMax=6",
        ]
        if verbose:
            options.insert(0, "-vv")
        return options

    def ssh(
        self,
        target: SshTarget,
        remote_command: str,
        *,
        timeout: int,
        check: bool = True,
        verbose: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        command = ["ssh", *self.ssh_options(target, verbose=verbose), f"root@{target.host}", remote_command]
        if self.mode == "wsl":
            command.insert(0, "wsl.exe")
        return self._run(command, timeout=timeout, check=check)

    def wait_until_ready(
        self,
        target: SshTarget,
        *,
        timeout: int,
        poll_interval: int,
        notify: ProgressCallback,
    ) -> None:
        deadline = time.monotonic() + timeout
        last_error = ""
        attempts = 0
        while time.monotonic() < deadline:
            attempts += 1
            result = self.ssh(target, "printf TRYON_SSH_OK", timeout=30, check=False)
            if result.returncode == 0 and "TRYON_SSH_OK" in (result.stdout or ""):
                notify("runpod-ssh-ready", 96, "SSH del Pod temporal está listo y la clave fue autenticada.")
                return
            last_error = (result.stderr or result.stdout or "SSH aún no disponible").strip()[-2000:]
            if attempts == 1 or attempts % 6 == 0:
                notify("runpod-ssh-wait", 96, f"Esperando autenticación SSH del Pod temporal (intento {attempts})…")
            time.sleep(poll_interval)

        diagnostic = self.ssh(target, "true", timeout=30, check=False, verbose=True)
        diagnostic_text = (diagnostic.stderr or diagnostic.stdout or last_error).strip()
        useful = "\n".join(diagnostic_text.splitlines()[-60:])[-7000:]
        raise RuntimeError(
            "No fue posible autenticar por SSH en el Pod temporal usando la clave privada configurada. "
            f"Diagnóstico SSH:\n{useful}"
        )

    def rsync(
        self,
        source_root: Path,
        target: SshTarget,
        remote_dir: str,
        *,
        overwrite: bool,
        timeout: int,
        notify: ProgressCallback,
    ) -> str:
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
                    pct = min(100, int(match.group(1))) if match else 0
                    notify("runpod-rsync", 96 + min(2, int(pct * 2 / 100)), f"Sincronizando por rsync: {clean[-500:]}")
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
