import json
import logging
from typing import Any

from app.core.config import settings
from app.schemas.i18n import (
    TranslationDictionaryResponse,
)
from app.services.i18n_service import (
    i18n_service,
)


logger = logging.getLogger(
    "app.i18n.cache"
)


class I18nDictionaryCacheService:
    CACHE_PREFIX = "i18n:dictionary"
    DEFAULT_TTL_SECONDS = 300

    def _redis_client(self):
        try:
            import redis

            redis_url = getattr(
                settings,
                "REDIS_URL",
                "redis://127.0.0.1:6379/0",
            )

            return redis.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )

        except Exception:
            logger.exception(
                "Could not create Redis client "
                "for i18n cache."
            )

            return None

    def _cache_key(
        self,
        locale_code: str,
    ) -> str:
        normalized = (
            i18n_service
            .normalize_locale_code(
                locale_code
            )
        )

        return (
            f"{self.CACHE_PREFIX}:"
            f"{normalized}"
        )

    def get_dictionary(
        self,
        db,
        *,
        locale_code: str,
    ) -> TranslationDictionaryResponse:
        cache_key = self._cache_key(
            locale_code
        )

        client = self._redis_client()

        if client is not None:
            try:
                cached = client.get(
                    cache_key
                )

                if cached:
                    parsed: dict[
                        str,
                        Any,
                    ] = json.loads(
                        cached
                    )

                    return (
                        TranslationDictionaryResponse(
                            **parsed
                        )
                    )

            except Exception:
                logger.warning(
                    "Could not read i18n "
                    "dictionary from Redis.",
                    exc_info=True,
                )

        dictionary = (
            i18n_service.dictionary(
                db,
                locale_code=locale_code,
            )
        )

        if client is not None:
            try:
                ttl_seconds = int(
                    getattr(
                        settings,
                        "I18N_CACHE_TTL_SECONDS",
                        self.DEFAULT_TTL_SECONDS,
                    )
                )

                client.setex(
                    cache_key,
                    ttl_seconds,
                    json.dumps(
                        dictionary.model_dump(),
                        ensure_ascii=False,
                        default=str,
                    ),
                )

            except Exception:
                logger.warning(
                    "Could not save i18n "
                    "dictionary in Redis.",
                    exc_info=True,
                )

        return dictionary

    def invalidate_locale(
        self,
        *,
        locale_code: str,
    ) -> bool:
        client = self._redis_client()

        if client is None:
            return False

        try:
            client.delete(
                self._cache_key(
                    locale_code
                )
            )

            return True

        except Exception:
            logger.warning(
                "Could not invalidate i18n locale.",
                exc_info=True,
            )

            return False

    def invalidate_all(
        self,
    ) -> int:
        client = self._redis_client()

        if client is None:
            return 0

        deleted = 0

        try:
            pattern = (
                f"{self.CACHE_PREFIX}:*"
            )

            for key in client.scan_iter(
                match=pattern,
                count=100,
            ):
                deleted += int(
                    client.delete(key)
                )

        except Exception:
            logger.warning(
                "Could not invalidate all "
                "i18n dictionaries.",
                exc_info=True,
            )

        return deleted


i18n_dictionary_cache_service = (
    I18nDictionaryCacheService()
)