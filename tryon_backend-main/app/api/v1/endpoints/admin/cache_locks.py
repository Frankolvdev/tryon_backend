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
from app.schemas.cache_lock import (
    CacheLockAcquireRequest,
    CacheLockAcquireResponse,
    CacheLockReleaseRequest,
    CacheLockReleaseResponse,
)
from app.services.audit_service import (
    audit_service,
)
from app.services.distributed_lock_service import (
    DistributedLock,
    distributed_lock_service,
)


router = APIRouter()


@router.post(
    "/cache-locks/acquire",
    response_model=CacheLockAcquireResponse,
)
def acquire_cache_lock(
    data: CacheLockAcquireRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    lock = distributed_lock_service.acquire(
        name=data.name,
        ttl_seconds=data.ttl_seconds,
        wait_timeout_seconds=(
            data.wait_timeout_seconds
        ),
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_cache_lock_acquired",
        entity_type="cache_lock",
        entity_id=data.name,
        description=(
            f"Attempted to acquire cache lock "
            f"{data.name}. Acquired: "
            f"{lock.acquired}."
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

    return CacheLockAcquireResponse(
        name=lock.name,
        owner=lock.owner,
        acquired=lock.acquired,
        ttl_seconds=lock.ttl_seconds,
    )


@router.post(
    "/cache-locks/release",
    response_model=CacheLockReleaseResponse,
)
def release_cache_lock(
    data: CacheLockReleaseRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    released = distributed_lock_service.release(
        DistributedLock(
            name=data.name,
            owner=data.owner,
            acquired=True,
            ttl_seconds=0,
        )
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_cache_lock_released",
        entity_type="cache_lock",
        entity_id=data.name,
        description=(
            f"Attempted to release cache lock "
            f"{data.name}. Released: "
            f"{released}."
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

    return CacheLockReleaseResponse(
        name=data.name,
        released=released,
    )