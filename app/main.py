from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.exception_handlers import (
    app_exception_handler,
    localized_exception_handler,
)
from app.api.v1.router import api_router
from app.common.exceptions import AppException
from app.common.localized_exceptions import (
    LocalizedApplicationException,
)
from app.core.config import settings
from app.middleware.abuse_detection_middleware import (
    AbuseDetectionMiddleware,
)
from app.middleware.i18n_middleware import I18nMiddleware
from app.middleware.rate_limit_middleware import (
    RateLimitMiddleware,
)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=getattr(
        settings,
        "DEBUG",
        False,
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

app.add_exception_handler(
    AppException,
    app_exception_handler,
)

app.add_exception_handler(
    LocalizedApplicationException,
    localized_exception_handler,
)


# ---------------------------------------------------------------------------
# CORS configuration
# ---------------------------------------------------------------------------

cors_origins = getattr(
    settings,
    "CORS_ORIGINS",
    [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
)

if isinstance(cors_origins, str):
    cors_origins = [
        origin.strip()
        for origin in cors_origins.split(",")
        if origin.strip()
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "Content-Language",
        "X-Resolved-Locale",
        "X-Locale-Source",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
        "X-RateLimit-Policy",
        "X-RateLimit-Redis-Available",
        "X-RateLimit-Fallback",
        "X-Anti-Abuse-Threshold",
        "X-Anti-Abuse-Rule",
        "Retry-After",
    ],
)


# ---------------------------------------------------------------------------
# Application middleware
#
# Starlette executes middleware in reverse registration order.
#
# Effective request order:
# 1. RateLimitMiddleware
# 2. I18nMiddleware
# 3. AbuseDetectionMiddleware
# 4. CORSMiddleware
# ---------------------------------------------------------------------------

app.add_middleware(
    AbuseDetectionMiddleware,
)

app.add_middleware(
    I18nMiddleware,
)

app.add_middleware(
    RateLimitMiddleware,
)


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

app.include_router(
    api_router,
    prefix="/api/v1",
)


# ---------------------------------------------------------------------------
# Root and health endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/",
    tags=["Root"],
)
def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
    }


@app.get(
    "/health",
    tags=["Health"],
)
def health():
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }