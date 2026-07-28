from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import threading
import venv
from pathlib import Path


class BeamCliEnvironmentService:
    """Provisiona Beam CLI en un entorno aislado del backend principal."""

    _lock = threading.Lock()

    @staticmethod
    def _project_root() -> Path:
        return Path(__file__).resolve().parents[2]

    @classmethod
    def requirements_path(cls) -> Path:
        return cls._project_root() / "requirements-beam.txt"

    @classmethod
    def environment_path(cls) -> Path:
        configured = str(os.environ.get("BEAM_PROVIDER_VENV") or "").strip()
        if configured:
            return Path(configured).expanduser().resolve()

        # El entorno aislado no debe crearse dentro del repositorio: cuando
        # Uvicorn se ejecuta con --reload, WatchFiles observa cada archivo que
        # pip instala y reinicia el backend en mitad de la operación.
        if os.name == "nt":
            base = Path(
                os.environ.get("LOCALAPPDATA")
                or os.environ.get("APPDATA")
                or Path.home()
            )
            return (base / "TryOn" / "provider_envs" / "beam").resolve()

        cache_home = str(os.environ.get("XDG_CACHE_HOME") or "").strip()
        base = Path(cache_home).expanduser() if cache_home else Path.home() / ".cache"
        return (base / "tryon" / "provider_envs" / "beam").resolve()

    @staticmethod
    def _beam_executable(environment_path: Path) -> Path:
        if os.name == "nt":
            return environment_path / "Scripts" / "beam.exe"
        return environment_path / "bin" / "beam"

    @staticmethod
    def _python_executable(environment_path: Path) -> Path:
        if os.name == "nt":
            return environment_path / "Scripts" / "python.exe"
        return environment_path / "bin" / "python"

    @classmethod
    def _requirements_digest(cls) -> str:
        path = cls.requirements_path()
        if not path.is_file():
            raise RuntimeError(f"No existe el archivo de dependencias de Beam: {path}")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @classmethod
    def find_existing(cls) -> str | None:
        override = str(os.environ.get("BEAM_CLI_EXECUTABLE") or "").strip()
        if override:
            path = Path(override).expanduser()
            if path.is_file():
                return str(path.resolve())

        isolated = cls._beam_executable(cls.environment_path())
        if isolated.is_file():
            return str(isolated)

        # Compatibilidad con instalaciones externas administradas por el operador.
        return shutil.which("beam")

    @classmethod
    def ensure(cls, *, timeout_seconds: int = 900) -> str:
        """Devuelve el CLI Beam, creando/actualizando su venv aislado si hace falta."""
        override = str(os.environ.get("BEAM_CLI_EXECUTABLE") or "").strip()
        if override:
            path = Path(override).expanduser()
            if not path.is_file():
                raise RuntimeError(f"BEAM_CLI_EXECUTABLE no existe: {path}")
            return str(path.resolve())

        with cls._lock:
            env_path = cls.environment_path()
            beam_executable = cls._beam_executable(env_path)
            python_executable = cls._python_executable(env_path)
            marker_path = env_path / ".requirements.sha256"
            expected_digest = cls._requirements_digest()
            current_digest = marker_path.read_text(encoding="utf-8").strip() if marker_path.is_file() else ""

            if beam_executable.is_file() and current_digest == expected_digest:
                return str(beam_executable)

            env_path.parent.mkdir(parents=True, exist_ok=True)
            if not python_executable.is_file():
                venv.EnvBuilder(with_pip=True, clear=False).create(env_path)

            command = [
                str(python_executable),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-input",
                "-r",
                str(cls.requirements_path()),
            ]
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=max(120, int(timeout_seconds)),
            )
            if completed.returncode != 0:
                output = (completed.stdout or "") + "\n" + (completed.stderr or "")
                raise RuntimeError(
                    "No fue posible instalar Beam CLI en su entorno aislado. "
                    + output.strip()[-5000:]
                )
            if not beam_executable.is_file():
                raise RuntimeError(
                    f"beam-client se instaló, pero no se encontró el ejecutable esperado: {beam_executable}"
                )

            marker_path.write_text(expected_digest, encoding="utf-8")
            return str(beam_executable)


beam_cli_environment_service = BeamCliEnvironmentService()
