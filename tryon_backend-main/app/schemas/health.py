from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DependencyHealthResponse(BaseModel):
    name: str
    status: str
    required: bool

    latency_ms: float | None = None
    message: str | None = None

    details: dict[str, Any] = Field(
        default_factory=dict,
    )


class LivenessResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str

    process_id: int
    uptime_seconds: float

    checked_at: datetime


class ReadinessResponse(BaseModel):
    status: str
    ready: bool

    dependencies: list[
        DependencyHealthResponse
    ]

    checked_at: datetime


class SystemHealthResponse(BaseModel):
    status: str
    ready: bool
    live: bool

    service: str
    version: str
    environment: str

    dependencies: list[
        DependencyHealthResponse
    ]

    summary: dict[str, int]

    checked_at: datetime