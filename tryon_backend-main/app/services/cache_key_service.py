import hashlib
import json
import re
from typing import Any

from app.common.cache_enums import CacheNamespace


class CacheKeyService:
    ROOT_PREFIX = "tryon-cache"
    VERSION = "v1"

    def _normalize_part(
        self,
        value: Any,
    ) -> str:
        if value is None:
            return "none"

        if isinstance(value, bool):
            return "true" if value else "false"

        if isinstance(value, (dict, list, tuple, set)):
            serialized = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
                separators=(",", ":"),
            )

            return hashlib.sha256(
                serialized.encode("utf-8")
            ).hexdigest()

        text = str(value).strip().lower()

        text = re.sub(
            r"[^a-z0-9._-]+",
            "-",
            text,
        )

        text = text.strip("-")

        if not text:
            return "empty"

        if len(text) > 120:
            digest = hashlib.sha256(
                text.encode("utf-8")
            ).hexdigest()

            return digest

        return text

    def build(
        self,
        namespace: CacheNamespace | str,
        *parts: Any,
    ) -> str:
        namespace_value = (
            namespace.value
            if isinstance(namespace, CacheNamespace)
            else self._normalize_part(namespace)
        )

        normalized_parts = [
            self._normalize_part(part)
            for part in parts
        ]

        key_parts = [
            self.ROOT_PREFIX,
            self.VERSION,
            namespace_value,
            *normalized_parts,
        ]

        return ":".join(key_parts)

    def namespace_pattern(
        self,
        namespace: CacheNamespace | str,
    ) -> str:
        namespace_value = (
            namespace.value
            if isinstance(namespace, CacheNamespace)
            else self._normalize_part(namespace)
        )

        return (
            f"{self.ROOT_PREFIX}:"
            f"{self.VERSION}:"
            f"{namespace_value}:*"
        )

    def namespace_prefix(
        self,
        namespace: CacheNamespace | str,
    ) -> str:
        namespace_value = (
            namespace.value
            if isinstance(namespace, CacheNamespace)
            else self._normalize_part(namespace)
        )

        return (
            f"{self.ROOT_PREFIX}:"
            f"{self.VERSION}:"
            f"{namespace_value}:"
        )

    def tag_key(
        self,
        tag: str,
    ) -> str:
        return (
            f"{self.ROOT_PREFIX}:"
            f"{self.VERSION}:"
            f"tag:"
            f"{self._normalize_part(tag)}"
        )

    def stats_key(
        self,
    ) -> str:
        return (
            f"{self.ROOT_PREFIX}:"
            f"{self.VERSION}:"
            "stats"
        )


cache_key_service = CacheKeyService()