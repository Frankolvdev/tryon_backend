import hmac

from fastapi import (
    Header,
    HTTPException,
    status,
)

from app.core.config import settings


def worker_guard(
    x_worker_api_key: str | None = Header(
        default=None,
        alias="X-Worker-API-Key",
    ),
) -> None:
    configured_key = getattr(
        settings,
        "WORKER_API_KEY",
        None,
    )

    if not configured_key:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "Worker API authentication "
                "is not configured."
            ),
        )

    if not x_worker_api_key:
        raise HTTPException(
            status_code=(
                status.HTTP_401_UNAUTHORIZED
            ),
            detail="Worker API key is required.",
        )

    if not hmac.compare_digest(
        str(x_worker_api_key),
        str(configured_key),
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_401_UNAUTHORIZED
            ),
            detail="Invalid worker API key.",
        )