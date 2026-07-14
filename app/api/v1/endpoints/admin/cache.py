from fastapi import (
    APIRouter,
    Depends,
    Request,
)
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import (
    admin_guard,
)
from app.models.user import User
from app.schemas.cache import (
    CacheAdminDeleteRequest,
    CacheAdminInvalidateNamespaceRequest,
    CacheAdminInvalidateTagRequest,
    CacheDeleteResult,
    CacheNamespaceInvalidationResult,
    CacheStatsResponse,
    CacheTagInvalidationResult,
)
from app.schemas.cache_operations import (
    CacheWarmupRequest,
    CacheWarmupResponse,
)
from app.schemas.runtime_cache import (
    RuntimeCacheInvalidateRequest,
    RuntimeCacheInvalidateResponse,
)
from app.services.audit_service import (
    audit_service,
)
from app.services.cache_invalidation_service import (
    cache_invalidation_service,
)
from app.services.cache_warmup_service import (
    cache_warmup_service,
)
from app.services.distributed_cache_service import (
    distributed_cache_service,
)
from app.services.integration_cache_service import (
    integration_cache_service,
)
from app.services.job_progress_cache_service import (
    job_progress_cache_service,
)
from app.services.presigned_url_cache_service import (
    presigned_url_cache_service,
)
from app.services.runpod_cache_service import (
    runpod_cache_service,
)
from app.services.tryon_cache_service import (
    tryon_cache_service,
)


router = APIRouter()


@router.get(
    "/cache/stats",
    response_model=CacheStatsResponse,
)
def get_cache_stats(
    current_admin: User = Depends(
        admin_guard
    ),
):
    return distributed_cache_service.get_stats()


@router.post(
    "/cache/warmup",
    response_model=CacheWarmupResponse,
)
def warmup_cache(
    data: CacheWarmupRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    result = cache_warmup_service.run(
        db,
        data=data,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_cache_warmup",
        entity_type="cache",
        entity_id=None,
        description=(
            "Executed cache warmup. "
            f"Loaded: {result.total_loaded_items}; "
            f"failures: {result.failures}."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return result


@router.post(
    "/cache/invalidate-runtime",
    response_model=RuntimeCacheInvalidateResponse,
)
def invalidate_runtime_cache(
    data: RuntimeCacheInvalidateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    invalidated_tags: list[str] = []
    deleted_keys = 0

    if data.tryon_job_id is not None:
        deleted_keys += (
            tryon_cache_service.invalidate_job(
                tryon_job_id=data.tryon_job_id
            )
        )

        invalidated_tags.append(
            f"tryon-job:{data.tryon_job_id}"
        )

    if data.provider_job_id:
        deleted_keys += (
            runpod_cache_service.invalidate_job(
                provider_job_id=(
                    data.provider_job_id
                )
            )
        )

        invalidated_tags.append(
            f"runpod-job:{data.provider_job_id}"
        )

    if data.integration_provider:
        deleted_keys += (
            integration_cache_service
            .invalidate_provider(
                provider=(
                    data.integration_provider
                )
            )
        )

        invalidated_tags.append(
            "integration:"
            + data.integration_provider
        )

    if data.storage_file_id is not None:
        deleted_keys += (
            presigned_url_cache_service
            .invalidate_file(
                storage_file_id=(
                    data.storage_file_id
                )
            )
        )

        invalidated_tags.append(
            f"storage-file:{data.storage_file_id}"
        )

    if data.background_job_public_id:
        deleted_keys += (
            job_progress_cache_service.invalidate(
                public_id=(
                    data.background_job_public_id
                )
            )
        )

        invalidated_tags.append(
            "background-job:"
            + data.background_job_public_id
        )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action=(
            "admin_runtime_cache_invalidated"
        ),
        entity_type="cache",
        entity_id=None,
        description=(
            "Invalidated runtime cache tags: "
            + ", ".join(invalidated_tags)
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return RuntimeCacheInvalidateResponse(
        invalidated_tags=invalidated_tags,
        deleted_keys=deleted_keys,
    )


@router.post(
    "/cache/invalidate-reference-data",
    response_model=CacheStatsResponse,
)
def invalidate_reference_data_cache(
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    (
        cache_invalidation_service
        .invalidate_all_reference_data()
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action=(
            "admin_reference_cache_invalidated"
        ),
        entity_type="cache",
        entity_id=None,
        description=(
            "Invalidated all reference-data "
            "cache namespaces."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return distributed_cache_service.get_stats()


@router.post(
    "/cache/delete",
    response_model=CacheDeleteResult,
)
def delete_cache_keys(
    data: CacheAdminDeleteRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    result = distributed_cache_service.delete_keys(
        data.keys
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_cache_keys_deleted",
        entity_type="cache",
        entity_id=None,
        description=(
            f"Deleted {result.deleted_count} "
            "cache key or keys."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return result


@router.post(
    "/cache/invalidate-tag",
    response_model=CacheTagInvalidationResult,
)
def invalidate_cache_tag(
    data: CacheAdminInvalidateTagRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    result = (
        distributed_cache_service
        .invalidate_tag(
            tag=data.tag
        )
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action=(
            "admin_cache_tag_invalidated"
        ),
        entity_type="cache_tag",
        entity_id=data.tag,
        description=(
            f"Invalidated cache tag "
            f"{data.tag}. Deleted "
            f"{result.deleted_count} keys."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return result


@router.post(
    "/cache/invalidate-namespace",
    response_model=(
        CacheNamespaceInvalidationResult
    ),
)
def invalidate_cache_namespace(
    data: CacheAdminInvalidateNamespaceRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    result = (
        distributed_cache_service
        .invalidate_namespace(
            namespace=data.namespace
        )
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action=(
            "admin_cache_namespace_invalidated"
        ),
        entity_type="cache_namespace",
        entity_id=data.namespace,
        description=(
            f"Invalidated cache namespace "
            f"{data.namespace}. Deleted "
            f"{result.deleted_count} keys."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return result