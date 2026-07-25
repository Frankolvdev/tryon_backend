import inspect
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.common.exceptions import (
    NotFoundException,
)
from app.jobs.account_security_jobs import (
    ACCOUNT_SECURITY_JOB_HANDLERS,
)
from app.jobs.audit_jobs import (
    AUDIT_JOB_HANDLERS,
)
from app.jobs.billing_jobs import (
    BILLING_JOB_HANDLERS,
)
from app.jobs.cache_jobs import (
    CACHE_JOB_HANDLERS,
)
from app.jobs.observability_jobs import (
    OBSERVABILITY_JOB_HANDLERS,
)
from app.jobs.security_jobs import (
    SECURITY_JOB_HANDLERS,
)
from app.jobs.user_notification_jobs import (
    USER_NOTIFICATION_JOB_HANDLERS,
)


def system_noop_handler(
    db: Session,
    *,
    message: str | None = None,
    **kwargs,
) -> dict[str, Any]:
    del db

    return {
        "success": True,
        "message": (
            message
            or "No-op job completed."
        ),
        "received": kwargs,
    }


def system_echo_handler(
    db: Session,
    *,
    payload: dict[str, Any] | None = None,
    **kwargs,
) -> dict[str, Any]:
    del db

    return {
        "success": True,
        "payload": payload or {},
        "received": kwargs,
    }


INTERNAL_JOB_HANDLERS: dict[
    str,
    Callable[..., Any],
] = {
    **ACCOUNT_SECURITY_JOB_HANDLERS,
    **AUDIT_JOB_HANDLERS,
    **BILLING_JOB_HANDLERS,
    **CACHE_JOB_HANDLERS,
    **OBSERVABILITY_JOB_HANDLERS,
    **SECURITY_JOB_HANDLERS,
    **USER_NOTIFICATION_JOB_HANDLERS,
    "system.noop": system_noop_handler,
    "system.echo": system_echo_handler,
}


class InternalJobHandlerRegistry:
    def list_handler_names(
        self,
    ) -> list[str]:
        return sorted(
            INTERNAL_JOB_HANDLERS.keys()
        )

    def exists(
        self,
        job_type: str,
    ) -> bool:
        return (
            job_type
            in INTERNAL_JOB_HANDLERS
        )

    def get(
        self,
        job_type: str,
    ) -> Callable[..., Any]:
        handler = (
            INTERNAL_JOB_HANDLERS.get(
                job_type
            )
        )

        if handler is None:
            raise NotFoundException(
                "Internal job handler "
                f"'{job_type}' is not "
                "registered."
            )

        return handler

    def execute(
        self,
        db: Session,
        *,
        job_type: str,
        payload: dict[str, Any],
    ) -> Any:
        handler = self.get(
            job_type
        )

        signature = inspect.signature(
            handler
        )

        parameters = (
            signature.parameters
        )

        accepts_kwargs = any(
            parameter.kind
            == inspect.Parameter.VAR_KEYWORD
            for parameter
            in parameters.values()
        )

        if accepts_kwargs:
            accepted_payload = dict(
                payload
            )

        else:
            accepted_payload = {
                key: value
                for key, value
                in payload.items()
                if key in parameters
            }

        return handler(
            db,
            **accepted_payload,
        )


internal_job_handler_registry = (
    InternalJobHandlerRegistry()
)