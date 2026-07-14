from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TryOnRuntimeCacheResponse(BaseModel):
    found: bool
    tryon_job_id: int
    value: dict[str, Any] | None = None
    ttl_seconds: int | None = None


class RunPodStatusCacheResponse(BaseModel):
    found: bool
    provider_job_id: str
    endpoint_id: str | None = None
    status: str | None = None
    value: dict[str, Any] | None = None
    ttl_seconds: int | None = None


class PresignedUrlCacheResponse(BaseModel):
    found: bool
    storage_file_id: int
    url: str | None = None
    expires_at: datetime | None = None
    ttl_seconds: int | None = None


class JobProgressCacheValue(BaseModel):
    job_id: int
    public_id: str
    status: str
    progress: float = Field(
        ge=0.0,
        le=100.0,
    )
    message: str | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )
    updated_at: datetime


class JobProgressCacheResponse(BaseModel):
    found: bool
    value: JobProgressCacheValue | None = None
    ttl_seconds: int | None = None


class RuntimeCacheInvalidateRequest(BaseModel):
    tryon_job_id: int | None = None
    provider_job_id: str | None = None
    integration_provider: str | None = None
    storage_file_id: int | None = None
    background_job_public_id: str | None = None


class RuntimeCacheInvalidateResponse(BaseModel):
    invalidated_tags: list[str] = Field(
        default_factory=list,
    )
    deleted_keys: int