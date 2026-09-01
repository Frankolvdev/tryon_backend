import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from sqlalchemy.orm import Session

from app.services.infrastructure_provider_service import InfrastructureProviderService


class ModalFileManagerError(RuntimeError):
    pass


class ModalFileManagerService:
    @classmethod
    def _config(cls, db: Session):
        config = InfrastructureProviderService.get_modal(db)
        if not config.enabled:
            raise ModalFileManagerError("El proveedor Modal no está activo.")
        if not config.token_id or not config.token_secret:
            raise ModalFileManagerError("Configura las credenciales de Modal.")
        executable = shutil.which("modal")
        if not executable:
            raise ModalFileManagerError("Modal CLI no está instalado en el backend. Ejecuta: pip install modal")
        return config, executable

    @classmethod
    def _run(cls, db: Session, args: list[str], timeout: int = 120, binary: bool = False):
        config, executable = cls._config(db)
        command = [executable, *args]
        if "--env" not in command and "-e" not in command:
            command.extend(["--env", config.environment])
        completed = subprocess.run(
            command,
            env=InfrastructureProviderService._modal_env(config),
            capture_output=True,
            text=not binary,
            timeout=timeout,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.decode(errors="replace") if binary else completed.stderr
            stdout = completed.stdout.decode(errors="replace") if binary else completed.stdout
            raise ModalFileManagerError((stderr or stdout or "Modal CLI terminó con error.")[-4000:])
        return completed

    @classmethod
    def list_volumes(cls, db: Session):
        config, _ = cls._config(db)
        return [{"name": config.volume_name, "driver": "modal", "mountpoint": "/vol", "labels": {"provider": "modal"}}]

    @classmethod
    def list_directory(cls, db: Session, volume: str, path: str = ""):
        config, _ = cls._config(db)
        # El File Manager solo debe operar sobre el volumen configurado por nombre.
        # Esto evita que un ID/hash residual de Docker se envíe a Modal durante el
        # cambio de proveedor en la interfaz.
        resolved_volume = config.volume_name
        clean = (path or "").strip("/\\")
        args = ["volume", "ls", resolved_volume]
        if clean:
            args.append(clean)
        args.append("--json")
        completed = cls._run(db, args)
        raw = (completed.stdout or "").strip()
        try:
            payload = json.loads(raw or "[]")
        except json.JSONDecodeError:
            payload = []
        rows = payload.get("entries", payload.get("items", payload.get("files", payload))) if isinstance(payload, dict) else payload
        items = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            normalized = {str(key).strip().lower().replace(" ", "_"): value for key, value in row.items()}
            raw_path = str(
                normalized.get("name")
                or normalized.get("filename")
                or normalized.get("file_name")
                or normalized.get("path")
                or ""
            )
            name = raw_path.rstrip("/").split("/")[-1]
            if not name:
                continue
            raw_type = str(normalized.get("type") or normalized.get("kind") or "").lower()
            is_dir = bool(
                normalized.get("is_dir")
                or normalized.get("is_directory")
                or raw_type in {"directory", "dir", "folder"}
                or raw_path.endswith("/")
            )
            child_path = "/".join(part for part in [clean, name] if part)
            raw_size = normalized.get("size") or normalized.get("size_bytes") or normalized.get("bytes") or 0
            try:
                size = int(raw_size)
            except (TypeError, ValueError):
                size = 0
            items.append({
                "name": name,
                "path": child_path,
                "type": "directory" if is_dir else "file",
                "size": size,
                "modified_at": (
                    normalized.get("modified_at")
                    or normalized.get("mtime")
                    or normalized.get("last_modified")
                    or normalized.get("created_at")
                ),
            })
        return {"volume": resolved_volume, "path": clean, "items": items}

    @classmethod
    def create_directory(cls, db: Session, volume: str, path: str):
        config, _ = cls._config(db)
        cls._run(db, ["volume", "mkdir", config.volume_name, path.strip("/\\")])
        return {"success": True, "volume": config.volume_name, "path": path}

    @classmethod
    def delete_path(cls, db: Session, volume: str, path: str):
        config, _ = cls._config(db)
        cls._run(db, ["volume", "rm", "-r", config.volume_name, path.strip("/\\")])
        return {"success": True, "volume": config.volume_name, "path": path}

    @classmethod
    def upload_bytes(cls, db: Session, volume: str, path: str, filename: str, content: bytes, overwrite: bool = True):
        config, _ = cls._config(db)
        resolved_volume = config.volume_name
        clean_path = (path or "").strip("/\\")
        destination = "/".join(part for part in [clean_path, Path(filename).name] if part)
        with tempfile.TemporaryDirectory(prefix="tryon-modal-upload-") as tmp:
            local = Path(tmp) / Path(filename).name
            local.write_bytes(content)
            args = ["volume", "put"]
            if overwrite:
                args.append("--force")
            args += [resolved_volume, str(local), destination]
            cls._run(db, args, timeout=3600)
        return {"success": True, "volume": resolved_volume, "path": destination, "size": len(content)}

    @classmethod
    def download_bytes(cls, db: Session, volume: str, path: str) -> bytes:
        config, _ = cls._config(db)
        resolved_volume = config.volume_name
        with tempfile.TemporaryDirectory(prefix="tryon-modal-download-") as tmp:
            destination = Path(tmp) / Path(path).name
            cls._run(db, ["volume", "get", resolved_volume, path.strip("/\\"), str(destination)], timeout=3600)
            if not destination.exists():
                candidates = list(Path(tmp).rglob("*"))
                files = [item for item in candidates if item.is_file()]
                if not files:
                    raise ModalFileManagerError("Modal no devolvió el archivo solicitado.")
                destination = files[0]
            return destination.read_bytes()

    @classmethod
    def copy_tree(
        cls,
        db: Session,
        source: Path,
        volume: str,
        destination_path: str,
        overwrite: bool = True,
        skip_identical: bool = False,
    ):
        config, _ = cls._config(db)
        resolved_volume = config.volume_name
        clean_destination = (destination_path or "").strip("/\\")
        remote_parent = f"{clean_destination}/" if clean_destination else "/"

        # Preserve the exact historical bulk-upload behavior unless the caller
        # explicitly requests "Omitir idénticos".
        if not skip_identical:
            children = sorted(source.iterdir(), key=lambda item: item.name.lower())
            for child in children:
                args = ["volume", "put"]
                if overwrite:
                    args.append("--force")
                args += [resolved_volume, str(child), remote_parent]
                cls._run(db, args, timeout=86400)
            return {
                "success": True,
                "volume": resolved_volume,
                "path": clean_destination,
                "items_uploaded": len(children),
                "items_skipped": 0,
            }

        uploaded = 0
        skipped = 0
        overwritten = 0
        directory_cache: dict[str, dict[str, dict]] = {}

        def remote_entries(parent: str) -> dict[str, dict]:
            clean_parent = parent.strip("/\\")
            cached = directory_cache.get(clean_parent)
            if cached is not None:
                return cached
            try:
                listing = cls.list_directory(db, resolved_volume, clean_parent)
            except ModalFileManagerError as exc:
                # A missing remote directory is equivalent to an empty one for
                # skip-identical purposes. Keep every other Modal error fatal.
                if "no such file or directory" not in str(exc).lower():
                    raise
                listing = {"items": []}
            mapped = {
                str(item.get("name") or ""): item
                for item in listing.get("items", [])
                if isinstance(item, dict)
            }
            directory_cache[clean_parent] = mapped
            return mapped

        for local_file in sorted(
            (item for item in source.rglob("*") if item.is_file()),
            key=lambda item: item.as_posix().casefold(),
        ):
            relative = local_file.relative_to(source).as_posix()
            remote_file = "/".join(
                part for part in (clean_destination, relative) if part
            )
            remote_dir = str(Path(remote_file).parent).replace("\\", "/")
            if remote_dir == ".":
                remote_dir = ""
            filename = Path(remote_file).name
            existing = remote_entries(remote_dir).get(filename)

            if existing is not None:
                remote_size = int(existing.get("size") or 0)
                if remote_size == local_file.stat().st_size:
                    skipped += 1
                    continue
                if not overwrite:
                    skipped += 1
                    continue

            args = ["volume", "put"]
            if existing is not None and overwrite:
                args.append("--force")
            args += [resolved_volume, str(local_file), remote_file]
            cls._run(db, args, timeout=86400)
            uploaded += 1
            if existing is not None:
                overwritten += 1

            # Keep cached directory coherent for a second file with same name.
            directory_cache.pop(remote_dir.strip("/\\"), None)

        return {
            "success": True,
            "volume": resolved_volume,
            "path": clean_destination,
            "items_uploaded": uploaded,
            "items_skipped": skipped,
            "items_overwritten": overwritten,
        }
