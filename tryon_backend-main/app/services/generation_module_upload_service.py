from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from starlette.datastructures import UploadFile
from sqlalchemy.orm import Session

from app.common.exceptions import AppException
from app.schemas.generation_module_runtime import GenerationModuleExecutionCreate
from app.services.generation_module_service import generation_module_service
from app.services.storage_service import storage_service


class GenerationModuleUploadService:
    async def parse_execution_request(
        self,
        db: Session,
        *,
        module_id: int,
        request: Request,
        user_id: int | None,
        forced_engine: Any | None = None,
    ) -> GenerationModuleExecutionCreate:
        content_type = (request.headers.get("content-type") or "").lower()
        if "multipart/form-data" not in content_type:
            try:
                body = await request.json()
            except Exception as exc:
                raise AppException("Invalid generation execution payload.") from exc
            data = GenerationModuleExecutionCreate.model_validate(body)
            return data.model_copy(update={"engine": forced_engine}) if forced_engine is not None else data

        form = await request.form()
        raw_payload = form.get("payload")
        if not isinstance(raw_payload, str):
            raise AppException("Multipart generation requests require a JSON 'payload' field.")
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            raise AppException("The generation payload is not valid JSON.") from exc

        data = GenerationModuleExecutionCreate.model_validate(payload)
        module = generation_module_service.get_response(db, module_id=module_id)
        definitions = {item.key: item for item in module.inputs}
        values = dict(data.inputs)

        file_keys = [str(value) for value in form.getlist("file_keys")]
        files = [value for value in form.getlist("files") if isinstance(value, UploadFile)]
        if len(file_keys) != len(files):
            raise AppException("Every uploaded file must include its matching input key.")
        if len(set(file_keys)) != len(file_keys):
            raise AppException("A generation file input may only be uploaded once.")

        for key, upload in zip(file_keys, files):
            definition = definitions.get(key)
            if definition is None:
                raise AppException(f"Unknown generation file input '{key}'.")
            if definition.input_type not in {"image", "file"}:
                raise AppException(f"Generation input '{key}' does not accept files.")
            self._validate_upload(definition, upload)
            stored = storage_service.save_upload_file(
                db=db,
                user_id=user_id,
                file=upload,
                folder=f"generation-inputs/{module.key}",
            )
            values[key] = {
                "__generation_file__": True,
                "storage_file_id": stored.id,
                "provider": stored.provider,
                "bucket": stored.bucket,
                "object_key": stored.object_key,
                "public_url": stored.public_url,
                "filename": stored.original_filename,
                "content_type": stored.content_type,
                "size_bytes": stored.size_bytes,
            }

        for definition in module.inputs:
            if definition.input_type in {"image", "file"} and definition.is_required and not values.get(definition.key):
                raise AppException(f"Required module input '{definition.key}' is missing.")

        update: dict[str, Any] = {"inputs": values}
        if forced_engine is not None:
            update["engine"] = forced_engine
        return data.model_copy(update=update)

    @staticmethod
    def _validate_upload(definition: Any, upload: UploadFile) -> None:
        rules = definition.validation or {}
        content_type = (upload.content_type or "application/octet-stream").lower()
        if definition.input_type == "image" and not content_type.startswith("image/"):
            raise AppException(f"Generation input '{definition.key}' requires an image file.")
        accepted = rules.get("accept")
        if isinstance(accepted, str) and accepted.strip():
            allowed = [item.strip().lower() for item in accepted.split(",") if item.strip()]
            filename = (upload.filename or "").lower()
            if not any(
                (item.endswith("/*") and content_type.startswith(item[:-1]))
                or item == content_type
                or (item.startswith(".") and filename.endswith(item))
                for item in allowed
            ):
                raise AppException(f"Generation input '{definition.key}' received an unsupported file type.")


generation_module_upload_service = GenerationModuleUploadService()
