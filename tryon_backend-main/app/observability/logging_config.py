import logging
import logging.config
import os
import sys
from typing import Any

from app.core.config import settings
from app.observability.json_formatter import (
    JsonLogFormatter,
)


_LOGGING_CONFIGURED = False


def _setting(
    name: str,
    default: Any,
) -> Any:
    return getattr(
        settings,
        name,
        default,
    )


def configure_logging(
    *,
    force: bool = False,
) -> None:
    global _LOGGING_CONFIGURED

    if _LOGGING_CONFIGURED and not force:
        return

    log_level = str(
        _setting(
            "LOG_LEVEL",
            "INFO",
        )
    ).upper()

    log_format = str(
        _setting(
            "LOG_FORMAT",
            "json",
        )
    ).lower()

    if log_format == "json":
        formatter_class = (
            "app.observability."
            "json_formatter."
            "JsonLogFormatter"
        )

        formatter_config: dict[str, Any] = {
            "()": formatter_class,
        }

    else:
        formatter_config = {
            "format": (
                "%(asctime)s | %(levelname)s | "
                "%(name)s | %(message)s"
            ),
        }

    configuration = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "application": formatter_config,
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "application",
                "stream": "ext://sys.stdout",
            },
        },
        "root": {
            "handlers": ["console"],
            "level": log_level,
        },
        "loggers": {
            "uvicorn": {
                "handlers": ["console"],
                "level": log_level,
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["console"],
                "level": log_level,
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["console"],
                "level": log_level,
                "propagate": False,
            },
            "sqlalchemy.engine": {
                "handlers": ["console"],
                "level": (
                    "INFO"
                    if bool(
                        _setting(
                            "LOG_SQL_QUERIES",
                            False,
                        )
                    )
                    else "WARNING"
                ),
                "propagate": False,
            },
            "httpx": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
        },
    }

    logging.config.dictConfig(
        configuration
    )

    logging.captureWarnings(True)

    _LOGGING_CONFIGURED = True

    logger = logging.getLogger(
        "app.observability"
    )

    logger.info(
        "Logging configured.",
        extra={
            "service": _setting(
                "APP_NAME",
                "tryon-backend",
            ),
            "environment": _setting(
                "ENVIRONMENT",
                "development",
            ),
            "log_level": log_level,
            "log_format": log_format,
            "process_id": os.getpid(),
            "python_version": (
                sys.version.split()[0]
            ),
        },
    )


def get_logger(
    name: str,
) -> logging.Logger:
    if not _LOGGING_CONFIGURED:
        configure_logging()

    return logging.getLogger(name)