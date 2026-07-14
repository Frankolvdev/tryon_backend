from typing import Any

from sqlalchemy.orm import Session

from app.services.unverified_account_cleanup_service import (
    unverified_account_cleanup_service,
)


def cleanup_unverified_accounts_handler(
    db: Session,
    *,
    batch_size: int = 500,
    **kwargs,
) -> dict[str, Any]:
    del kwargs

    return (
        unverified_account_cleanup_service
        .run(
            db,
            batch_size=batch_size,
        )
    )


ACCOUNT_SECURITY_JOB_HANDLERS = {
    "account_security.cleanup_unverified": (
        cleanup_unverified_accounts_handler
    ),
}