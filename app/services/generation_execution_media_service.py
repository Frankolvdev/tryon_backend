from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.schemas.generation_module_runtime import GenerationModuleExecutionResponse
from app.repositories.storage_file_repository import storage_file_repository
from app.services.storage_service import storage_service


class GenerationExecutionMediaService:
    """Adds short-lived readable URLs to execution snapshots without persisting them."""

    URL_FIELDS = ("preview_url", "download_url", "public_url", "source_url", "url")

    def hydrate(self, db: Session, execution: GenerationModuleExecutionResponse) -> GenerationModuleExecutionResponse:
        item = execution.model_copy(deep=True)
        item.inputs = self._hydrate_value(db, item.inputs)
        item.outputs = self._hydrate_value(db, item.outputs)
        item.context = self._hydrate_value(db, item.context)
        item.steps = [
            step.model_copy(update={"outputs": self._hydrate_value(db, step.outputs)}, deep=True)
            for step in item.steps
        ]
        return item

    def hydrate_many(self, db: Session, executions: list[GenerationModuleExecutionResponse]) -> list[GenerationModuleExecutionResponse]:
        return [self.hydrate(db, execution) for execution in executions]

    def _hydrate_value(self, db: Session, value: Any) -> Any:
        if isinstance(value, list):
            return [self._hydrate_value(db, item) for item in value]
        if not isinstance(value, dict):
            return value

        hydrated = {key: self._hydrate_value(db, nested) for key, nested in value.items()}
        storage_file_id = hydrated.get("storage_file_id")
        try:
            file_id = int(storage_file_id) if storage_file_id is not None else None
        except (TypeError, ValueError):
            file_id = None

        if file_id:
            storage_file = storage_file_repository.get_by_id(db, file_id)
            if storage_file is not None:
                readable_url = storage_service.create_presigned_url(
                    db,
                    storage_file=storage_file,
                    expires_in_seconds=3600,
                )
                if readable_url:
                    # Replace every transport URL. The stored snapshot keeps the durable
                    # file id/provider/object key; only the API response receives this URL.
                    hydrated["preview_url"] = readable_url
                    hydrated["download_url"] = readable_url
                    hydrated["public_url"] = readable_url
                    if "source_url" in hydrated:
                        hydrated["source_url"] = readable_url
                    if "url" in hydrated:
                        hydrated["url"] = readable_url
                hydrated.setdefault("provider", storage_file.provider)
                hydrated.setdefault("bucket", storage_file.bucket)
                hydrated.setdefault("object_key", storage_file.object_key)
                hydrated.setdefault("filename", storage_file.original_filename)
                hydrated.setdefault("content_type", storage_file.content_type)
                hydrated.setdefault("size_bytes", storage_file.size_bytes)
        return hydrated


generation_execution_media_service = GenerationExecutionMediaService()
