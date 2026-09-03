from __future__ import annotations

import base64
import mimetypes
import re
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.common.exceptions import AppException, NotFoundException
from app.repositories.storage_file_repository import storage_file_repository
from app.services.comfyui_local_adapter_service import ComfyUILocalAdapterService, comfyui_local_adapter_service
from app.services.storage_service import storage_service


class GenerationModuleFileMaterializerService:
    """Turns persisted generation uploads into engine-specific inputs."""

    def _safe_name(self, filename: str | None, *, fallback: str) -> str:
        original = Path(filename or fallback)
        stem = re.sub(r"[^A-Za-z0-9._-]+", "-", original.stem).strip(".-") or fallback
        suffix = re.sub(r"[^A-Za-z0-9.]", "", original.suffix)[:16]
        return f"{stem}{suffix}"

    def _read_bytes(self, db: Session, reference: dict[str, Any]) -> tuple[bytes, str, str]:
        local_path = reference.get("local_path")
        if local_path:
            source = Path(str(local_path))
            if not source.is_file():
                raise NotFoundException("The temporary generation file is missing.")
            filename = self._safe_name(reference.get("filename") or source.name, fallback="runtime-input")
            content_type = reference.get("content_type") or mimetypes.guess_type(filename)[0] or "application/octet-stream"
            return source.read_bytes(), filename, content_type

        storage_file_id = reference.get("storage_file_id")
        if not storage_file_id:
            raise AppException("Generation file reference is missing storage_file_id or local_path.")
        stored = storage_file_repository.get_by_id(db, int(storage_file_id))
        if stored is None:
            raise NotFoundException("Generation input file was not found.")

        content = storage_service.read_bytes(db, storage_file=stored)

        filename = self._safe_name(stored.original_filename, fallback=f"input-{stored.id}")
        content_type = stored.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return content, filename, content_type

    def materialize_local(
        self,
        db: Session,
        *,
        execution_id: UUID,
        module_input_key: str,
        reference: dict[str, Any],
        adapter: ComfyUILocalAdapterService | None = None,
        engine: str = "local_docker",
    ) -> dict[str, Any]:
        content, filename, content_type = self._read_bytes(db, reference)
        subfolder = f"generation-modules/{execution_id}"
        target_adapter = adapter or comfyui_local_adapter_service
        uploaded = target_adapter.upload_input(
            content=content,
            filename=filename,
            content_type=content_type,
            subfolder=subfolder,
        )
        relative_name = "/".join(part for part in [uploaded.get("subfolder"), uploaded.get("name")] if part)
        return {
            "module_input_key": module_input_key,
            "engine": engine,
            "filename": uploaded.get("name") or filename,
            "subfolder": uploaded.get("subfolder") or subfolder,
            "relative_name": relative_name or filename,
            "type": uploaded.get("type") or "input",
            "content_type": content_type,
            "size_bytes": len(content),
        }

    def materialize_runpod(
        self,
        db: Session,
        *,
        execution_id: UUID,
        module_input_key: str,
        reference: dict[str, Any],
    ) -> dict[str, Any]:
        content, filename, content_type = self._read_bytes(db, reference)
        target_name = f"generation-modules/{execution_id}/{filename}"
        public_url = reference.get("public_url")
        payload: dict[str, Any] = {
            "module_input_key": module_input_key,
            "filename": filename,
            "target_name": target_name,
            "content_type": content_type,
            "size_bytes": len(content),
        }
        if public_url and str(public_url).startswith(("http://", "https://")):
            payload["source_url"] = public_url
            payload["transport"] = "url"
        else:
            payload["content_base64"] = base64.b64encode(content).decode("ascii")
            payload["transport"] = "base64"
        return payload


generation_module_file_materializer_service = GenerationModuleFileMaterializerService()
