from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.storage_service import storage_service


class GenerationModuleResultService:
    def register_files(
        self,
        db: Session,
        *,
        execution_id: UUID,
        user_id: int | None,
        files: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        registered: list[dict[str, Any]] = []
        for position, item in enumerate(files):
            enriched = dict(item)
            if enriched.get("storage_file_id"):
                registered.append(enriched)
                continue
            local_path = enriched.get("local_path")
            if not local_path:
                registered.append(enriched)
                continue
            path = Path(str(local_path))
            if not path.is_file():
                registered.append(enriched)
                continue
            content_type = enriched.get("content_type") or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            record = storage_service.save_bytes(
                db=db,
                user_id=user_id,
                content=path.read_bytes(),
                original_filename=enriched.get("filename") or path.name,
                content_type=content_type,
                folder=f"generation-results/{execution_id}",
            )
            enriched.update(
                {
                    "storage_file_id": record.id,
                    "provider": record.provider,
                    "bucket": record.bucket,
                    "object_key": record.object_key,
                    "public_url": record.public_url,
                    "filename": record.original_filename,
                    "content_type": record.content_type,
                    "size_bytes": record.size_bytes,
                    "result_position": position,
                    "download_url": record.public_url,
                }
            )
            registered.append(enriched)
        return registered


generation_module_result_service = GenerationModuleResultService()
