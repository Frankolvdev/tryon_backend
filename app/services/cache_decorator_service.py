from collections.abc import Callable
from functools import wraps
from typing import Any

from app.common.cache_enums import (
    CacheNamespace,
)
from app.services.distributed_cache_service import (
    distributed_cache_service,
)


class CacheDecoratorService:
    def cached(
        self,
        *,
        namespace: CacheNamespace | str,
        key_builder: Callable[..., list[Any]],
        ttl_seconds: int = 300,
        tags_builder: Callable[..., list[str]]
        | None = None,
    ):
        def decorator(function):
            @wraps(function)
            def wrapper(*args, **kwargs):
                parts = key_builder(
                    *args,
                    **kwargs,
                )

                tags = (
                    tags_builder(
                        *args,
                        **kwargs,
                    )
                    if tags_builder
                    else []
                )

                return (
                    distributed_cache_service
                    .remember(
                        namespace=namespace,
                        parts=parts,
                        loader=lambda: function(
                            *args,
                            **kwargs,
                        ),
                        ttl_seconds=ttl_seconds,
                        tags=tags,
                    )
                )

            return wrapper

        return decorator


cache_decorator_service = (
    CacheDecoratorService()
)