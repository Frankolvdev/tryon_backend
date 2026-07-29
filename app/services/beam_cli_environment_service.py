from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


class BeamCliEnvironmentService:
    """Resuelve Beam CLI desde el mismo entorno Python del backend.

    Beam se instala como una dependencia normal del backend, igual que Modal.
    Este servicio nunca crea entornos virtuales, nunca ejecuta ``pip install``
    y nunca modifica paquetes mientras Uvicorn está ejecutándose.
    """

    @staticmethod
    def _backend_python() -> Path:
        return Path(sys.executable).resolve()

    @classmethod
    def _backend_beam_executable(cls) -> Path:
        python_executable = cls._backend_python()
        if os.name == "nt":
            return python_executable.parent / "beam.exe"
        return python_executable.parent / "beam"

    @staticmethod
    def _run(command: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=max(5, int(timeout)),
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"La comprobación de Beam CLI excedió {max(5, int(timeout))} segundos."
            ) from exc

    @classmethod
    def _validate_backend_installation(cls, executable: Path) -> None:
        python_executable = cls._backend_python()
        diagnostic = cls._run(
            [
                str(python_executable),
                "-c",
                "import packaging; import beam; import beam.cli.main; print('ok')",
            ],
            timeout=30,
        )
        if diagnostic.returncode != 0:
            output = "\n".join(
                part.strip()
                for part in (diagnostic.stdout, diagnostic.stderr)
                if part and part.strip()
            )
            raise RuntimeError(
                "Beam no está instalado correctamente en el mismo venv del backend. "
                "Activa el venv del backend y ejecuta: "
                "pip install -r requirements.txt. Detalle: "
                + output[-4000:]
            )

        if not executable.is_file():
            raise RuntimeError(
                "Beam está importable, pero no existe el ejecutable Beam dentro del "
                f"venv activo del backend: {executable}. Activa ese venv y ejecuta: "
                "pip install --force-reinstall beam-client==0.2.201"
            )

    @classmethod
    def find_existing(cls) -> str | None:
        """Devuelve únicamente el Beam CLI del entorno activo del backend."""
        override = str(os.environ.get("BEAM_CLI_EXECUTABLE") or "").strip()
        if override:
            override_path = Path(override).expanduser().resolve()
            if override_path.is_file():
                cls._validate_backend_installation(override_path)
                return str(override_path)

        executable = cls._backend_beam_executable()
        try:
            cls._validate_backend_installation(executable)
        except RuntimeError:
            return None
        return str(executable)

    @classmethod
    def ensure(cls, *, timeout_seconds: int = 30) -> str:
        """Obtiene Beam CLI del venv activo sin instalar ni actualizar paquetes."""
        del timeout_seconds  # Se conserva la firma para no afectar a consumidores Beam.

        override = str(os.environ.get("BEAM_CLI_EXECUTABLE") or "").strip()
        executable = Path(override).expanduser().resolve() if override else cls._backend_beam_executable()
        cls._validate_backend_installation(executable)
        return str(executable)


beam_cli_environment_service = BeamCliEnvironmentService()
