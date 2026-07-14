from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CacheEntryMetadata(BaseModel):
    key: str
    namespace: str
    ttl_seconds: int | None
    expires_at: datetime | None
    tags: list[str] = Field(default_factory=list)


class CacheGetResult(BaseModel):
    found: bool
    key: str
    namespace: str
    value: Any | None = None
    ttl_seconds: int | None = None


class CacheSetResult(BaseModel):
    stored: bool
    key: str
    namespace: str
    ttl_seconds: int | None
    tags: list[str] = Field(default_factory=list)


class CacheDeleteResult(BaseModel):
    deleted: bool
    deleted_count: int
    keys: list[str] = Field(default_factory=list)


class CacheTagInvalidationResult(BaseModel):
    tag: str
    deleted_count: int
    keys: list[str] = Field(default_factory=list)


class CacheNamespaceInvalidationResult(BaseModel):
    namespace: str
    deleted_count: int


class CacheStatsResponse(BaseModel):
    redis_available: bool

    hits: int
    misses: int
    sets: int
    deletes: int
    errors: int

    hit_rate: float

    tracked_namespaces: list[str]
    generated_at: datetime


class CacheKeyCreate(BaseModel):
    namespace: str = Field(
        min_length=1,
        max_length=100,
    )

    parts: list[str | int] = Field(
        default_factory=list,
    )


class CacheAdminDeleteRequest(BaseModel):
    keys: list[str] = Field(
        min_length=1,
        max_length=1000,
    )


class CacheAdminInvalidateTagRequest(BaseModel):
    tag: str = Field(
        min_length=1,
        max_length=200,
    )


class CacheAdminInvalidateNamespaceRequest(BaseModel):
    namespace: str = Field(
        min_length=1,
        max_length=100,
    )