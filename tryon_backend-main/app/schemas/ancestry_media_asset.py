from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

StorageMode = Literal["auto", "local", "amazon_s3", "cloudflare_r2"]


class AncestryAssetCreate(BaseModel):
    ancestry_key: str = Field(min_length=1, max_length=120)
    display_name: str = Field(min_length=1, max_length=180)
    country_code: str | None = Field(default=None, max_length=8)
    flag_emoji: str | None = Field(default=None, max_length=16)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    sort_order: float = 100.0
    storage_mode: StorageMode = "auto"
    is_active: bool = True
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AncestryAssetUpdate(BaseModel):
    ancestry_key: str | None = Field(default=None, min_length=1, max_length=120)
    display_name: str | None = Field(default=None, min_length=1, max_length=180)
    country_code: str | None = Field(default=None, max_length=8)
    flag_emoji: str | None = Field(default=None, max_length=16)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    sort_order: float | None = None
    storage_mode: StorageMode | None = None
    is_active: bool | None = None
    notes: str | None = None
    metadata: dict[str, Any] | None = None


class AncestryAssetResponse(BaseModel):
    id: int
    ancestry_key: str
    display_name: str
    country_code: str | None
    flag_emoji: str | None
    latitude: float | None
    longitude: float | None
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


class AncestryAssetListResponse(BaseModel):
    items: list[AncestryAssetResponse]
    total: int


class AncestryStorageOptionsResponse(BaseModel):
    active_provider: str
    modes: list[str]
