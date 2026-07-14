from typing import Any

from redis.exceptions import RedisError

from app.common.time import utc_now
from app.core.redis_client import redis_client
from app.schemas.cache_health import (
    CacheMaintenanceRequest,
    CacheMaintenanceResponse,
)
from app.services.cache_key_service import (
    cache_key_service,
)
from app.services.distributed_cache_service import (
    distributed_cache_service,
)


class CacheMaintenanceService:
    def _decode(
        self,
        value: Any,
    ) -> str:
        if isinstance(value, bytes):
            return value.decode(
                "utf-8",
                errors="replace",
            )

        return str(value)

    def _tag_pattern(
        self,
    ) -> str:
        return (
            f"{cache_key_service.ROOT_PREFIX}:"
            f"{cache_key_service.VERSION}:"
            "tag:*"
        )

    def run(
        self,
        *,
        data: CacheMaintenanceRequest,
    ) -> CacheMaintenanceResponse:
        started_at = utc_now()

        scanned_tag_sets = 0
        orphan_members_removed = 0
        empty_tag_sets_deleted = 0

        namespace_deleted: str | None = None
        namespace_deleted_keys = 0

        errors: list[
            dict[str, Any]
        ] = []

        try:
            client = redis_client.get_client()

            if (
                data.clean_orphan_tag_members
                or data.clean_empty_tag_sets
            ):
                for raw_tag_key in client.scan_iter(
                    match=self._tag_pattern(),
                    count=data.scan_count,
                ):
                    if (
                        scanned_tag_sets
                        >= data.max_tag_sets
                    ):
                        break

                    scanned_tag_sets += 1

                    tag_key = self._decode(
                        raw_tag_key
                    )

                    try:
                        raw_members = (
                            client.smembers(
                                tag_key
                            )
                        )

                        existing_members: list[
                            str
                        ] = []

                        orphan_members: list[
                            str
                        ] = []

                        for raw_member in raw_members:
                            member = self._decode(
                                raw_member
                            )

                            if client.exists(member):
                                existing_members.append(
                                    member
                                )
                            else:
                                orphan_members.append(
                                    member
                                )

                        if (
                            data.clean_orphan_tag_members
                            and orphan_members
                        ):
                            removed = int(
                                client.srem(
                                    tag_key,
                                    *orphan_members,
                                )
                            )

                            orphan_members_removed += (
                                removed
                            )

                        remaining_count = int(
                            client.scard(
                                tag_key
                            )
                        )

                        if (
                            data.clean_empty_tag_sets
                            and remaining_count == 0
                        ):
                            empty_tag_sets_deleted += int(
                                client.delete(
                                    tag_key
                                )
                            )

                    except RedisError as error:
                        errors.append(
                            {
                                "tag_key": tag_key,
                                "error": str(error),
                            }
                        )

            if data.delete_namespace:
                namespace_result = (
                    distributed_cache_service
                    .invalidate_namespace(
                        namespace=(
                            data.delete_namespace
                        ),
                        scan_count=data.scan_count,
                    )
                )

                namespace_deleted = (
                    namespace_result.namespace
                )

                namespace_deleted_keys = (
                    namespace_result
                    .deleted_count
                )

        except RedisError as error:
            errors.append(
                {
                    "task": (
                        "cache_maintenance"
                    ),
                    "error": str(error),
                }
            )

        return CacheMaintenanceResponse(
            success=len(errors) == 0,
            scanned_tag_sets=(
                scanned_tag_sets
            ),
            orphan_members_removed=(
                orphan_members_removed
            ),
            empty_tag_sets_deleted=(
                empty_tag_sets_deleted
            ),
            namespace_deleted=(
                namespace_deleted
            ),
            namespace_deleted_keys=(
                namespace_deleted_keys
            ),
            errors=errors,
            started_at=started_at,
            completed_at=utc_now(),
        )


cache_maintenance_service = (
    CacheMaintenanceService()
)