from typing import Any

from sqlalchemy.orm import Session

from app.schemas.cache_health import (
    CacheMaintenanceRequest,
)
from app.services.cache_health_service import (
    cache_health_service,
)
from app.services.cache_maintenance_service import (
    cache_maintenance_service,
)


def cache_maintenance_handler(
    db: Session,
    *,
    clean_orphan_tag_members: bool = True,
    clean_empty_tag_sets: bool = True,
    delete_namespace: str | None = None,
    scan_count: int = 500,
    max_tag_sets: int = 1000,
    **kwargs,
) -> dict[str, Any]:
    del db
    del kwargs

    result = cache_maintenance_service.run(
        data=CacheMaintenanceRequest(
            clean_orphan_tag_members=(
                clean_orphan_tag_members
            ),
            clean_empty_tag_sets=(
                clean_empty_tag_sets
            ),
            delete_namespace=(
                delete_namespace
            ),
            scan_count=scan_count,
            max_tag_sets=max_tag_sets,
        )
    )

    return {
        "success": result.success,
        "maintenance": result.model_dump(
            mode="json"
        ),
    }


def cache_health_check_handler(
    db: Session,
    **kwargs,
) -> dict[str, Any]:
    del db
    del kwargs

    result = (
        cache_health_service
        .run_health_check()
    )

    return {
        "success": (
            result.status == "healthy"
        ),
        "health": result.model_dump(
            mode="json"
        ),
    }


CACHE_JOB_HANDLERS = {
    "cache.maintenance": (
        cache_maintenance_handler
    ),
    "cache.health_check": (
        cache_health_check_handler
    ),
}