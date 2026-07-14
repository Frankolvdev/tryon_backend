import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Any

from app.observability.context import (
    get_correlation_id,
    get_request_context,
)


class JsonLogFormatter(logging.Formatter):
    RESERVED_FIELDS = {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }

    SENSITIVE_KEYS = {
        "authorization",
        "access_token",
        "refresh_token",
        "api_key",
        "apikey",
        "password",
        "password_hash",
        "hashed_password",
        "secret",
        "secret_key",
        "stripe_secret_key",
        "runpod_api_key",
        "worker_api_key",
        "cookie",
        "set-cookie",
    }

    def _timestamp(
        self,
        record: logging.LogRecord,
    ) -> str:
        return datetime.fromtimestamp(
            record.created,
            tz=timezone.utc,
        ).isoformat()

    def _sanitize(
        self,
        value: Any,
        *,
        key: str | None = None,
    ) -> Any:
        normalized_key = (
            key.lower().replace("-", "_")
            if key
            else None
        )

        if (
            normalized_key
            and normalized_key
            in self.SENSITIVE_KEYS
        ):
            return "[REDACTED]"

        if isinstance(value, dict):
            return {
                str(item_key): self._sanitize(
                    item_value,
                    key=str(item_key),
                )
                for item_key, item_value
                in value.items()
            }

        if isinstance(value, (list, tuple, set)):
            return [
                self._sanitize(item)
                for item in value
            ]

        if isinstance(
            value,
            (
                str,
                int,
                float,
                bool,
            ),
        ) or value is None:
            return value

        return str(value)

    def _exception_data(
        self,
        record: logging.LogRecord,
    ) -> dict[str, Any] | None:
        if not record.exc_info:
            return None

        exception_type = (
            record.exc_info[0].__name__
            if record.exc_info[0]
            else None
        )

        exception_message = (
            str(record.exc_info[1])
            if record.exc_info[1]
            else None
        )

        formatted_traceback = "".join(
            traceback.format_exception(
                *record.exc_info
            )
        )

        return {
            "type": exception_type,
            "message": exception_message,
            "traceback": formatted_traceback,
        }

    def _extra_fields(
        self,
        record: logging.LogRecord,
    ) -> dict[str, Any]:
        extra: dict[str, Any] = {}

        for key, value in record.__dict__.items():
            if key in self.RESERVED_FIELDS:
                continue

            if key.startswith("_"):
                continue

            extra[key] = self._sanitize(
                value,
                key=key,
            )

        return extra

    def format(
        self,
        record: logging.LogRecord,
    ) -> str:
        correlation_id = (
            get_correlation_id()
        )

        request_data = (
            get_request_context()
        )

        payload: dict[str, Any] = {
            "timestamp": self._timestamp(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id,
            "service": getattr(
                record,
                "service",
                None,
            ),
            "environment": getattr(
                record,
                "environment",
                None,
            ),
        }

        if request_data:
            payload["request"] = self._sanitize(
                request_data
            )

        extra = self._extra_fields(record)

        if extra:
            payload["context"] = extra

        exception = self._exception_data(
            record
        )

        if exception:
            payload["exception"] = exception

        if record.stack_info:
            payload["stack_info"] = (
                record.stack_info
            )

        return json.dumps(
            payload,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        )