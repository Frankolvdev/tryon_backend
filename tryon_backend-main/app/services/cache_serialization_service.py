import base64
import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class CacheSerializationService:
    TYPE_KEY = "__cache_type__"
    VALUE_KEY = "value"

    def _json_default(
        self,
        value: Any,
    ) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump(
                mode="json"
            )

        if isinstance(value, datetime):
            return {
                self.TYPE_KEY: "datetime",
                self.VALUE_KEY: value.isoformat(),
            }

        if isinstance(value, date):
            return {
                self.TYPE_KEY: "date",
                self.VALUE_KEY: value.isoformat(),
            }

        if isinstance(value, Decimal):
            return {
                self.TYPE_KEY: "decimal",
                self.VALUE_KEY: str(value),
            }

        if isinstance(value, UUID):
            return {
                self.TYPE_KEY: "uuid",
                self.VALUE_KEY: str(value),
            }

        if isinstance(value, Enum):
            return value.value

        if isinstance(value, bytes):
            return {
                self.TYPE_KEY: "bytes",
                self.VALUE_KEY: base64.b64encode(
                    value
                ).decode("ascii"),
            }

        if isinstance(value, set):
            return list(value)

        raise TypeError(
            f"Unsupported cache value type: "
            f"{value.__class__.__name__}"
        )

    def _object_hook(
        self,
        value: dict[str, Any],
    ) -> Any:
        cache_type = value.get(
            self.TYPE_KEY
        )

        if not cache_type:
            return value

        raw_value = value.get(
            self.VALUE_KEY
        )

        if cache_type == "datetime":
            return datetime.fromisoformat(
                raw_value
            )

        if cache_type == "date":
            return date.fromisoformat(
                raw_value
            )

        if cache_type == "decimal":
            return Decimal(raw_value)

        if cache_type == "uuid":
            return UUID(raw_value)

        if cache_type == "bytes":
            return base64.b64decode(
                raw_value
            )

        return value

    def serialize(
        self,
        value: Any,
    ) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            default=self._json_default,
        )

    def deserialize(
        self,
        value: str | bytes,
    ) -> Any:
        if isinstance(value, bytes):
            value = value.decode("utf-8")

        return json.loads(
            value,
            object_hook=self._object_hook,
        )


cache_serialization_service = (
    CacheSerializationService()
)