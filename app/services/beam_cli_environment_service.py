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
        if os.name == "nt":
            base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
            return (base / "TryOn" / "provider_envs" / "beam").resolve()
        base = Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache"))
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
    def _environment_ready(cls, environment_path: Path) -> bool:
        beam_executable = cls._beam_executable(environment_path)
        python_executable = cls._python_executable(environment_path)
        if not beam_executable.is_file() or not python_executable.is_file():
            return False
        completed = subprocess.run(
            [str(python_executable), "-c", "import packaging; import beam.cli.main"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return completed.returncode == 0

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

            if current_digest == expected_digest and cls._environment_ready(env_path):
                return str(beam_executable)

            env_path.parent.mkdir(parents=True, exist_ok=True)
            if not python_executable.is_file():
                venv.EnvBuilder(with_pip=True, clear=False).create(env_path)

            bootstrap = subprocess.run(
                [
                    str(python_executable), "-m", "pip", "install",
                    "--disable-pip-version-check", "--no-input", "--upgrade",
                    "pip", "setuptools", "wheel", "packaging>=23,<27",
                ],
                capture_output=True,
                text=True,
                timeout=max(120, int(timeout_seconds)),
            )
            if bootstrap.returncode != 0:
                output = (bootstrap.stdout or "") + "\n" + (bootstrap.stderr or "")
                raise RuntimeError("No fue posible preparar las dependencias base de Beam CLI. " + output.strip()[-5000:])

            command = [
                str(python_executable), "-m", "pip", "install",
                "--disable-pip-version-check", "--no-input", "--upgrade",
                "-r", str(cls.requirements_path()),
            ]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=max(120, int(timeout_seconds)))
            if completed.returncode != 0:
                output = (completed.stdout or "") + "\n" + (completed.stderr or "")
                raise RuntimeError(
                    "No fue posible instalar Beam CLI en su entorno aislado. "
                    + output.strip()[-5000:]
                )
            if not cls._environment_ready(env_path):
                raise RuntimeError(
                    "Beam CLI se instaló, pero su entorno quedó incompleto. "
                    "Falta alguna dependencia requerida por el propio CLI."
                )

            marker_path.write_text(expected_digest, encoding="utf-8")
            return str(beam_executable)


beam_cli_environment_service = BeamCliEnvironmentService()
