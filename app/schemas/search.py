from typing import Any

from pydantic import BaseModel, Field


class SearchResultItem(BaseModel):
    entity: str
    id: str
    title: str
    description: str | None = None
    url: str | None = None
    relevance_score: int = 0
    metadata: dict[str, Any] = {}


class SearchResponse(BaseModel):
    query: str
    page: int
    page_size: int
    total: int
    items: list[SearchResultItem]


class AdvancedSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    entities: list[str] | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    filters: dict[str, Any] = {}