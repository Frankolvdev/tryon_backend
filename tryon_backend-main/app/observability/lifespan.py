from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.services.metrics_collection_service import (
    metrics_collection_service,
)


@asynccontextmanager
async def application_lifespan(
    app: FastAPI,
):
    del app

    enabled = bool(
        getattr(
            settings,
            "METRICS_BACKGROUND_COLLECTION_ENABLED",
            True,
        )
    )

    interval_seconds = int(
        getattr(
            settings,
            "METRICS_COLLECTION_INTERVAL_SECONDS",
            30,
        )
    )

    if enabled:
        metrics_collection_service.start(
            interval_seconds=interval_seconds,
        )

    try:
        yield

    finally:
        metrics_collection_service.stop()