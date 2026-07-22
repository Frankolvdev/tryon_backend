from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.generation_module import GenerationModuleCreate, GenerationModuleResponse
from app.schemas.generation_module_runtime import GenerationModuleExecutionResponse


class GenerationModuleCloneRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    activate: bool = False


class GenerationModulePublishRequest(BaseModel):
    deactivate_other_versions: bool = True


class GenerationModuleImportRequest(BaseModel):
    module: GenerationModuleCreate
    replace_existing: bool = False


class GenerationModuleExportResponse(BaseModel):
    format_version: int = 1
    module: dict[str, Any]


class GenerationModuleVersionListResponse(BaseModel):
    items: list[GenerationModuleResponse]
    total: int


class GenerationExecutionListResponse(BaseModel):
    items: list[GenerationModuleExecutionResponse]
    total: int
    skip: int
    limit: int


class GenerationExecutionRetryRequest(BaseModel):
    engine: str | None = None


class GenerationExecutionDeleteResponse(BaseModel):
    execution_id: UUID
    deleted: bool = True
