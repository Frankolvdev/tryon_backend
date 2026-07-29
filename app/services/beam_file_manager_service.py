from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.services.beam_cli_environment_service import beam_cli_environment_service
from app.services.beam_credentials_service import beam_credentials_service
from app.services.infrastructure_provider_service import InfrastructureProviderService


class BeamFileManagerError(RuntimeError):
    pass


class BeamFileManagerService:
    """File Manager de Beam aislado del resto de proveedores.

    La CLI actual usa tres formatos distintos:
    - ``beam volume ...`` para administrar volúmenes.
    - ``beam ls/rm/mv volumen/ruta`` para operar dentro del volumen.
    - ``beam cp ... beam://volumen`` para transferencias locales.

    En Windows, Beam CLI 0.2.x puede convertir destinos ``beam://volumen/ruta``
    en rutas con ``\\`` y confundir todo el texto con el nombre del volumen.
    Por eso los uploads se copian primero a la raíz y después se mueven con
    ``beam mv`` a la ruta final.
    """

    ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
    SEPARATOR_RE = re.compile(r"^[\s─━═\-]+$")
    SIZE_UNITS = {
        "B": 1,
        "KB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "TB": 1000**4,
        "KIB": 1024,
        "MIB": 1024**2,
        "GIB": 1024**3,
        "TIB": 1024**4,
    }

    @classmethod
    def _env(cls, db: Session):
        cfg = InfrastructureProviderService.get_beam(db)
        try:
            beam_credentials_service.require_token(cfg)
        except Exception as exc:
            raise BeamFileManagerError(str(exc)) from exc

        executable = beam_cli_environment_service.ensure(timeout_seconds=30)
        home = tempfile.mkdtemp(prefix="tryon-beam-file-manager-")
        env = os.environ.copy()
        env.update({"HOME": home, "USERPROFILE": home})
        try:
            auth = beam_credentials_service.configure_cli(
                executable=executable,
                config=cfg,
                env=env,
                timeout_seconds=45,
            )
        except Exception as exc:
            shutil.rmtree(home, ignore_errors=True)
            raise BeamFileManagerError(str(exc)) from exc
        return cfg, executable, auth.env, home

    @classmethod
    def _run(cls, db: Session, args: list[str], timeout: int = 3600):
        cfg, executable, env, home = cls._env(db)
        try:
            try:
                completed = subprocess.run(
                    [executable, *args],
                    env=env,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=max(10, int(timeout)),
                )
            except subprocess.TimeoutExpired as exc:
                raise BeamFileManagerError(
                    f"Beam CLI excedió {max(10, int(timeout))} segundos ejecutando: "
                    + " ".join(args)
                ) from exc

            output = "\n".join(
                part.strip()
                for part in (completed.stdout, completed.stderr)
                if part and part.strip()
            )
            if completed.returncode != 0:
                raise BeamFileManagerError(
                    (output or "Beam CLI terminó con error")[-6000:]
                )
            return cfg, output
        finally:
            shutil.rmtree(home, ignore_errors=True)

    @staticmethod
    def _clean(path: str | None) -> str:
        return "/".join(
            part
            for part in str(path or "").replace("\\", "/").split("/")
            if part not in {"", ".", ".."}
        )

    @classmethod
    def _volume_name(cls, cfg: Any, requested: str | None = None) -> str:
        """Devuelve siempre el volumen oficial guardado para Beam.

        ``requested`` se conserva únicamente para no romper la firma consumida por
        los endpoints existentes. Nunca se utiliza como identificador operativo:
        la interfaz puede abreviar visualmente el nombre con puntos suspensivos y
        ese texto no debe llegar a una comparación ni a Beam CLI.
        """
        del requested
        configured = cls._clean(str(getattr(cfg, "volume_name", "") or ""))
        if not configured:
            raise BeamFileManagerError("Configura el nombre del volumen Beam.")
        return configured

    @classmethod
    def _cli_path(cls, volume: str, path: str | None = None) -> str:
        clean = cls._clean(path)
        return volume + (f"/{clean}" if clean else "")

    @classmethod
    def _uri(cls, volume: str, path: str | None = None) -> str:
        clean = cls._clean(path)
        return f"beam://{volume}" + (f"/{clean}" if clean else "")

    @classmethod
    def _parse_size(cls, value: str) -> int:
        match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)", value.strip())
        if not match:
            return 0
        multiplier = cls.SIZE_UNITS.get(match.group(2).upper(), 1)
        return int(float(match.group(1)) * multiplier)

    @classmethod
    def _table_rows(cls, output: str) -> list[list[str]]:
        rows: list[list[str]] = []
        clean_output = cls.ANSI_RE.sub("", output or "")
        for line in clean_output.splitlines():
            raw = line.strip()
            if not raw or cls.SEPARATOR_RE.fullmatch(raw):
                continue
            lower = raw.casefold()
            if lower.startswith(("name ", "=>", "welcome ")):
                continue
            if re.match(r"^\d+\s+(?:item|items|volume|volumes)\b", lower):
                continue
            columns = [part.strip() for part in re.split(r"\s{2,}", raw) if part.strip()]
            if columns:
                rows.append(columns)
        return rows

    @classmethod
    def list_volumes(cls, db: Session):
        cfg, output = cls._run(db, ["volume", "list"], 120)
        configured = cls._volume_name(cfg)
        items: list[dict[str, Any]] = []
        for columns in cls._table_rows(output):
            name = columns[0]
            if not name or name.casefold() == "name":
                continue
            size = 0
            if len(columns) > 1:
                # La columna Size puede ser "0.00 B" o no existir según versión.
                size = cls._parse_size(columns[1])
            items.append(
                {
                    "name": name,
                    "driver": "beam",
                    "mountpoint": "/models",
                    "scope": "global",
                    "labels": {"provider": "beam", "configured": name == configured},
                    "options": {"size_bytes": size},
                }
            )
        return items

    @classmethod
    def list_directory(cls, db: Session, volume: str, path: str = ""):
        cfg = InfrastructureProviderService.get_beam(db)
        selected = cls._volume_name(cfg, volume)
        clean = cls._clean(path)
        # Beam ls espera volumen/ruta, no beam://volumen/ruta.
        _, output = cls._run(db, ["ls", cls._cli_path(selected, clean)], 300)
        items: list[dict[str, Any]] = []
        for columns in cls._table_rows(output):
            if len(columns) < 2:
                continue
            name = columns[0].rstrip("/")
            if not name or name in {".", "..", ".keep"}:
                continue
            is_dir_value = columns[-1].casefold()
            is_dir = is_dir_value in {"yes", "true", "dir", "directory"} or columns[0].endswith("/")
            size_text = " ".join(columns[1:3]) if len(columns) >= 3 else columns[1]
            size = 0 if is_dir else cls._parse_size(size_text)
            child = "/".join(part for part in (clean, name) if part)
            items.append(
                {
                    "name": name,
                    "path": child,
                    "type": "directory" if is_dir else "file",
                    "size": size,
                    "modified_at": None,
                }
            )
        return {"volume": selected, "path": clean, "items": items}

    @classmethod
    def _upload_via_root(
        cls,
        db: Session,
        *,
        volume: str,
        local_path: Path,
        destination: str,
        timeout: int,
    ) -> None:
        destination_clean = cls._clean(destination)
        if not destination_clean:
            raise BeamFileManagerError("La ruta de destino Beam está vacía.")

        suffix = local_path.suffix
        staging_name = f".tryon-upload-{uuid.uuid4().hex}{suffix}"
        with tempfile.TemporaryDirectory(prefix="tryon-beam-stage-") as tmp:
            staged_local = Path(tmp) / staging_name
            shutil.copy2(local_path, staged_local)
            # En Windows solo usamos beam://volumen en cp; las rutas anidadas se
            # resuelven después con mv para evitar el bug de barras invertidas.
            cls._run(db, ["cp", str(staged_local), cls._uri(volume)], timeout)

        staging_remote = cls._cli_path(volume, staging_name)
        destination_remote = cls._cli_path(volume, destination_clean)
        try:
            cls._run(db, ["mv", staging_remote, destination_remote], 600)
        except Exception:
            try:
                cls._run(db, ["rm", staging_remote], 120)
            except Exception:
                pass
            raise

    @classmethod
    def create_directory(cls, db: Session, volume: str, path: str):
        cfg = InfrastructureProviderService.get_beam(db)
        selected = cls._volume_name(cfg, volume)
        clean = cls._clean(path)
        if not clean:
            raise BeamFileManagerError("La ruta de la carpeta Beam está vacía.")
        with tempfile.TemporaryDirectory(prefix="tryon-beam-mkdir-") as tmp:
            marker = Path(tmp) / ".keep"
            marker.write_bytes(b"")
            cls._upload_via_root(
                db,
                volume=selected,
                local_path=marker,
                destination=f"{clean}/.keep",
                timeout=300,
            )
        return {"success": True, "volume": selected, "path": clean}

    @classmethod
    def upload_file(cls, db: Session, volume: str, path: str, local_path: Path):
        cfg = InfrastructureProviderService.get_beam(db)
        selected = cls._volume_name(cfg, volume)
        destination = cls._clean(path)
        cls._upload_via_root(
            db,
            volume=selected,
            local_path=Path(local_path),
            destination=destination,
            timeout=max(3600, int(cfg.timeout_seconds)),
        )
        return {
            "success": True,
            "volume": selected,
            "path": destination,
            "size": Path(local_path).stat().st_size,
        }

    @classmethod
    def download_to_temp(cls, db: Session, volume: str, path: str):
        cfg = InfrastructureProviderService.get_beam(db)
        selected = cls._volume_name(cfg, volume)
        clean = cls._clean(path)
        tmp = Path(tempfile.mkdtemp(prefix="tryon-beam-download-"))
        target = tmp / Path(clean).name
        cls._run(
            db,
            ["cp", cls._uri(selected, clean), str(target)],
            max(3600, int(cfg.timeout_seconds)),
        )
        if not target.is_file():
            # Algunas versiones crean el archivo dentro del directorio destino.
            candidates = [candidate for candidate in tmp.rglob("*") if candidate.is_file()]
            if len(candidates) == 1:
                target = candidates[0]
            else:
                raise BeamFileManagerError("Beam terminó la descarga, pero no se encontró el archivo local.")
        return target

    @classmethod
    def delete_path(cls, db: Session, volume: str, path: str):
        cfg = InfrastructureProviderService.get_beam(db)
        selected = cls._volume_name(cfg, volume)
        clean = cls._clean(path)
        if not clean:
            raise BeamFileManagerError("No se permite eliminar la raíz del volumen Beam.")
        remote = cls._cli_path(selected, clean)
        try:
            cls._run(db, ["rm", remote], 600)
        except BeamFileManagerError as first_error:
            # Compatibilidad con versiones que todavía requieren -r para carpetas.
            try:
                cls._run(db, ["rm", "-r", remote], 600)
            except BeamFileManagerError:
                raise first_error
        return {"success": True, "volume": selected, "path": clean}

    @classmethod
    def transfer(cls, db: Session, source: str, destination: str, operation: str):
        cfg = InfrastructureProviderService.get_beam(db)
        selected = cls._volume_name(cfg)
        source_clean = cls._clean(source)
        destination_clean = cls._clean(destination)
        if not source_clean or not destination_clean:
            raise BeamFileManagerError("La ruta de origen y destino son obligatorias.")

        source_remote = cls._cli_path(selected, source_clean)
        destination_remote = cls._cli_path(selected, destination_clean)
        normalized_operation = str(operation or "copy").casefold()
        if normalized_operation == "move":
            cls._run(db, ["mv", source_remote, destination_remote], 600)
        elif normalized_operation == "copy":
            # Beam no documenta una copia remota-a-remota estable. Descargamos a
            # temporal y reutilizamos el upload blindado para no duplicar/mover el original.
            local = cls.download_to_temp(db, selected, source_clean)
            try:
                cls._upload_via_root(
                    db,
                    volume=selected,
                    local_path=local,
                    destination=destination_clean,
                    timeout=max(3600, int(cfg.timeout_seconds)),
                )
            finally:
                shutil.rmtree(local.parent, ignore_errors=True)
        else:
            raise BeamFileManagerError(f"Operación Beam no soportada: {operation}")
        return {
            "success": True,
            "operation": normalized_operation,
            "source_path": source_clean,
            "destination_path": destination_clean,
        }

    @classmethod
    def rename(cls, db: Session, path: str, new_name: str):
        clean = cls._clean(path)
        safe_name = Path(str(new_name or "")).name.strip()
        if not clean or not safe_name or safe_name in {".", ".."}:
            raise BeamFileManagerError("El nuevo nombre no es válido.")
        parent = "/".join(clean.split("/")[:-1])
        destination = "/".join(part for part in (parent, safe_name) if part)
        return cls.transfer(db, clean, destination, "move")
