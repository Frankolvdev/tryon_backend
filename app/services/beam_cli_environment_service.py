from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import threading
import venv
from pathlib import Path


class BeamCliEnvironmentService:
    """Provisiona Beam CLI sin bloquear las acciones del proveedor.

    Prioriza una instalación existente y funcional. El entorno aislado solo se
    crea como fallback y queda fuera del repositorio para no disparar reloads.
    """

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

    @staticmethod
    def _run(command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=max(10, int(timeout)),
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"La preparación de Beam CLI excedió {max(10, int(timeout))} segundos."
            ) from exc

    @classmethod
    def _external_cli_ready(cls, executable: str) -> bool:
        """Valida el CLI sin ejecutar comandos interactivos.

        En versiones actuales de Beam, ``beam --help`` puede iniciar el flujo de
        bienvenida y esperar ``Token:`` cuando todavía no existe un contexto.
        Por eso la comprobación se limita a verificar el ejecutable; el entorno
        aislado se valida importando el módulo con su propio Python.
        """
        try:
            path = Path(executable)
            return path.is_file() if path.is_absolute() else shutil.which(executable) is not None
        except Exception:
            return False

    @classmethod
    def _environment_ready(cls, environment_path: Path) -> bool:
        beam_executable = cls._beam_executable(environment_path)
        python_executable = cls._python_executable(environment_path)
        if not beam_executable.is_file() or not python_executable.is_file():
            return False
        try:
            completed = cls._run(
                [
                    str(python_executable),
                    "-c",
                    "import packaging; import beam.cli.main",
                ],
                timeout=30,
            )
            return completed.returncode == 0
        except Exception:
            return False

    @classmethod
    def find_existing(cls) -> str | None:
        override = str(os.environ.get("BEAM_CLI_EXECUTABLE") or "").strip()
        if override:
            path = Path(override).expanduser()
            if path.is_file() and cls._external_cli_ready(str(path.resolve())):
                return str(path.resolve())

        isolated = cls._beam_executable(cls.environment_path())
        if isolated.is_file() and cls._environment_ready(cls.environment_path()):
            return str(isolated)

        external = shutil.which("beam")
        if external and cls._external_cli_ready(external):
            return external
        return None

    @classmethod
    def _install_isolated(cls, env_path: Path, *, timeout_seconds: int) -> str:
        beam_executable = cls._beam_executable(env_path)
        python_executable = cls._python_executable(env_path)
        marker_path = env_path / ".requirements.sha256"
        expected_digest = cls._requirements_digest()

        env_path.parent.mkdir(parents=True, exist_ok=True)
        if not python_executable.is_file():
            venv.EnvBuilder(with_pip=True, clear=False).create(env_path)

        # Reparación rápida del error real observado: Beam importa packaging al
        # arrancar. No se actualiza pip/setuptools en cada clic, porque eso era
        # lo que podía dejar la petición bloqueada durante muchos minutos.
        packaging_check = cls._run(
            [str(python_executable), "-c", "import packaging"],
            timeout=20,
        )
        if packaging_check.returncode != 0:
            packaging_install = cls._run(
                [
                    str(python_executable),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--no-input",
                    "packaging>=23,<27",
                ],
                timeout=min(max(60, int(timeout_seconds)), 300),
            )
            if packaging_install.returncode != 0:
                output = ((packaging_install.stdout or "") + "\n" + (packaging_install.stderr or "")).strip()
                raise RuntimeError(
                    "No fue posible instalar la dependencia 'packaging' requerida por Beam CLI. "
                    + output[-5000:]
                )

        current_digest = marker_path.read_text(encoding="utf-8").strip() if marker_path.is_file() else ""
        if current_digest != expected_digest or not cls._environment_ready(env_path):
            completed = cls._run(
                [
                    str(python_executable),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--no-input",
                    "-r",
                    str(cls.requirements_path()),
                ],
                timeout=min(max(120, int(timeout_seconds)), 600),
            )
            if completed.returncode != 0:
                output = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()
                raise RuntimeError(
                    "No fue posible instalar Beam CLI en su entorno aislado. "
                    + output[-5000:]
                )

        if not cls._environment_ready(env_path):
            diagnostic = cls._run(
                [
                    str(python_executable),
                    "-c",
                    "import packaging; import beam.cli.main; print('ok')",
                ],
                timeout=30,
            )
            output = ((diagnostic.stdout or "") + "\n" + (diagnostic.stderr or "")).strip()
            raise RuntimeError(
                "Beam CLI se instaló, pero no puede iniciar correctamente. "
                + output[-5000:]
            )

        marker_path.write_text(expected_digest, encoding="utf-8")
        return str(beam_executable)

    @classmethod
    def ensure(cls, *, timeout_seconds: int = 900) -> str:
        """Devuelve un Beam CLI funcional sin reinstalarlo en cada acción."""
        existing = cls.find_existing()
        if existing:
            return existing

        with cls._lock:
            # Otra petición pudo terminar la preparación mientras esperábamos.
            existing = cls.find_existing()
            if existing:
                return existing
            return cls._install_isolated(
                cls.environment_path(),
                timeout_seconds=timeout_seconds,
            )


beam_cli_environment_service = BeamCliEnvironmentService()
