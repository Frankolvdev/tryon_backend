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
        completed = subprocess.run(
            [executable, *args],
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
        clean = (path or "").strip("/\\")
        args = ["volume", "ls", volume]
        if clean:
            args.append(clean)
        args.append("--json")
        completed = cls._run(db, args)
        raw = (completed.stdout or "").strip()
        try:
            payload = json.loads(raw or "[]")
        except json.JSONDecodeError:
            payload = []
        rows = payload.get("entries", payload.get("items", payload)) if isinstance(payload, dict) else payload
        items = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or row.get("path") or "").rstrip("/").split("/")[-1]
            if not name:
                continue
            is_dir = bool(row.get("is_dir") or row.get("type") in {"directory", "dir"} or str(row.get("path", "")).endswith("/"))
            child_path = "/".join(part for part in [clean, name] if part)
            items.append({
                "name": name,
                "path": child_path,
                "type": "directory" if is_dir else "file",
                "size": int(row.get("size") or row.get("size_bytes") or 0),
                "modified_at": row.get("modified_at") or row.get("mtime"),
            })
        return {"volume": volume, "path": clean, "items": items}

    @classmethod
    def create_directory(cls, db: Session, volume: str, path: str):
        cls._run(db, ["volume", "mkdir", volume, path.strip("/\\")])
        return {"success": True, "volume": volume, "path": path}

    @classmethod
    def delete_path(cls, db: Session, volume: str, path: str):
        cls._run(db, ["volume", "rm", "-r", volume, path.strip("/\\")])
        return {"success": True, "volume": volume, "path": path}

    @classmethod
    def upload_bytes(cls, db: Session, volume: str, path: str, filename: str, content: bytes, overwrite: bool = True):
        destination = (path or Path(filename).name).strip("/\\")
        with tempfile.TemporaryDirectory(prefix="tryon-modal-upload-") as tmp:
            local = Path(tmp) / Path(filename).name
            local.write_bytes(content)
            args = ["volume", "put"]
            if overwrite:
                args.append("--force")
            args += [volume, str(local), destination]
            cls._run(db, args, timeout=3600)
        return {"success": True, "volume": volume, "path": destination, "size": len(content)}

    @classmethod
    def download_bytes(cls, db: Session, volume: str, path: str) -> bytes:
        with tempfile.TemporaryDirectory(prefix="tryon-modal-download-") as tmp:
            destination = Path(tmp) / Path(path).name
            cls._run(db, ["volume", "get", volume, path.strip("/\\"), str(destination)], timeout=3600)
            if not destination.exists():
                candidates = list(Path(tmp).rglob("*"))
                files = [item for item in candidates if item.is_file()]
                if not files:
                    raise ModalFileManagerError("Modal no devolvió el archivo solicitado.")
                destination = files[0]
            return destination.read_bytes()

    @classmethod
    def copy_tree(cls, db: Session, source: Path, volume: str, destination_path: str, overwrite: bool = True):
        args = ["volume", "put"]
        if overwrite:
            args.append("--force")
        args += [volume, str(source), (destination_path or "/").strip("/\\") or "/"]
        cls._run(db, args, timeout=86400)
