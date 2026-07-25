from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.inspection import inspect


class AuditSnapshotService:
    SENSITIVE_FIELDS = {
        "password",
        "password_hash",
        "hashed_password",
        "current_password",
        "new_password",
        "confirm_password",
        "access_token",
        "refresh_token",
        "token",
        "api_key",
        "secret",
        "secret_key",
        "client_secret",
        "private_key",
        "stripe_secret_key",
        "stripe_webhook_secret",
        "runpod_api_key",
        "worker_api_key",
        "authorization",
        "cookie",
        "set_cookie",
        "card_number",
        "card_cvc",
        "cvc",
        "cvv",
    }

    REDACTED_VALUE = "[REDACTED]"

    def _normalized_field_name(
        self,
        field_name: str,
    ) -> str:
        return (
            field_name
            .strip()
            .lower()
            .replace("-", "_")
            .replace(" ", "_")
        )

    def _is_sensitive(
        self,
        field_name: str,
    ) -> bool:
        normalized = self._normalized_field_name(
            field_name
        )

        if normalized in self.SENSITIVE_FIELDS:
            return True

        sensitive_fragments = (
            "password",
            "secret",
            "private_key",
            "access_token",
            "refresh_token",
            "api_key",
            "authorization",
        )

        return any(
            fragment in normalized
            for fragment in sensitive_fragments
        )

    def _serialize_value(
        self,
        value: Any,
        *,
        field_name: str | None = None,
    ) -> Any:
        if (
            field_name
            and self._is_sensitive(field_name)
        ):
            return self.REDACTED_VALUE

        if value is None:
            return None

        if isinstance(
            value,
            (
                str,
                int,
                float,
                bool,
            ),
        ):
            return value

        if isinstance(value, Decimal):
            return str(value)

        if isinstance(value, datetime):
            return value.isoformat()

        if isinstance(value, date):
            return value.isoformat()

        if isinstance(value, UUID):
            return str(value)

        if isinstance(value, Enum):
            return self._serialize_value(
                value.value
            )

        if isinstance(value, BaseModel):
            return self.snapshot(
                value.model_dump()
            )

        if is_dataclass(value):
            return self.snapshot(
                asdict(value)
            )

        if isinstance(value, dict):
            return {
                str(key): self._serialize_value(
                    item,
                    field_name=str(key),
                )
                for key, item in value.items()
            }

        if isinstance(
            value,
            (
                list,
                tuple,
                set,
            ),
        ):
            return [
                self._serialize_value(item)
                for item in value
            ]

        return str(value)

    def _sqlalchemy_snapshot(
        self,
        value: Any,
    ) -> dict[str, Any] | None:
        try:
            mapper = inspect(
                value.__class__
            )

        except Exception:
            return None

        result: dict[str, Any] = {}

        for column in mapper.columns:
            field_name = column.key

            try:
                field_value = getattr(
                    value,
                    field_name,
                )

            except Exception:
                continue

            result[field_name] = (
                self._serialize_value(
                    field_value,
                    field_name=field_name,
                )
            )

        return result

    def snapshot(
        self,
        value: Any,
    ) -> dict[str, Any] | None:
        if value is None:
            return None

        if isinstance(value, dict):
            return {
                str(key): self._serialize_value(
                    item,
                    field_name=str(key),
                )
                for key, item in value.items()
            }

        if isinstance(value, BaseModel):
            return self.snapshot(
                value.model_dump()
            )

        if is_dataclass(value):
            return self.snapshot(
                asdict(value)
            )

        sqlalchemy_result = (
            self._sqlalchemy_snapshot(value)
        )

        if sqlalchemy_result is not None:
            return sqlalchemy_result

        if hasattr(value, "__dict__"):
            return {
                str(key): self._serialize_value(
                    item,
                    field_name=str(key),
                )
                for key, item
                in vars(value).items()
                if not str(key).startswith("_")
            }

        return {
            "value": self._serialize_value(
                value
            )
        }


audit_snapshot_service = AuditSnapshotService()