from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

StorageMode = Literal["auto", "local", "amazon_s3", "cloudflare_r2"]
ToolKey = Literal["eyebrows", "lips", "hairstyle"]


class ModelGenerationAssetCreate(BaseModel):
    tool_key: ToolKey
    asset_key: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=180)
    value: str = Field(min_length=1, max_length=500)
    sort_order: float = 100.0
    storage_mode: StorageMode = "auto"
    is_active: bool = True
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelGenerationAssetUpdate(BaseModel):
    asset_key: str | None = Field(default=None, min_length=1, max_length=120)
    title: str | None = Field(default=None, min_length=1, max_length=180)
    value: str | None = Field(default=None, min_length=1, max_length=500)
    sort_order: float | None = None
    storage_mode: StorageMode | None = None
    is_active: bool | None = None
    notes: str | None = None
    metadata: dict[str, Any] | None = None


class ModelGenerationAssetResponse(BaseModel):
    id: int
    tool_key: str
    asset_key: str
    title: str
    value: str
    sort_order: float
    storage_mode: str
    poster_storage_file_id: int | None
    video_storage_file_id: int | None
    poster_url: str | None = None
    video_url: str | None = None
    is_active: bool
    notes: str | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ModelGenerationAssetListResponse(BaseModel):
    items: list[ModelGenerationAssetResponse]
    total: int


class ModelGenerationStorageOptionsResponse(BaseModel):
    active_provider: str
    modes: list[str]
