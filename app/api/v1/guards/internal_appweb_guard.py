import hmac

from fastapi import Header, HTTPException, status

from app.core.config import settings


def internal_appweb_guard(
    x_appweb_internal_key: str | None = Header(
        default=None,
        alias="X-Appweb-Internal-Key",
    ),
) -> None:
    """Authorize server-to-server calls from AppWeb.

    This credential must exist only in the AppWeb server environment and must
    never use a NEXT_PUBLIC_ variable. End-user JWTs intentionally do not grant
    access to these internal resources.
    """
    configured_key = settings.APPWEB_INTERNAL_KEY
    if not configured_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal AppWeb authentication is not configured.",
        )
    if not x_appweb_internal_key or not hmac.compare_digest(
        str(x_appweb_internal_key), str(configured_key)
    ):
        # Do not disclose whether an internal endpoint exists.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
