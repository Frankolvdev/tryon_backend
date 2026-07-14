from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.auth_guard import auth_guard
from app.models.user import User
from app.repositories.background_job_repository import (
    background_job_repository,
)
from app.schemas.runtime_cache import (
    JobProgressCacheResponse,
    JobProgressCacheValue,
)
from app.services.job_progress_cache_service import (
    job_progress_cache_service,
)


router = APIRouter()


@router.get(
    "/{public_id}",
    response_model=JobProgressCacheResponse,
)
def get_background_job_progress(
    public_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    cached = job_progress_cache_service.get(
        public_id=public_id
    )

    if cached.found:
        return cached

    job = (
        background_job_repository
        .get_by_public_id(
            db,
            public_id,
        )
    )

    if not job or job.user_id != current_user.id:
        return JobProgressCacheResponse(
            found=False,
            value=None,
            ttl_seconds=None,
        )

    value = job_progress_cache_service.store(
        job_id=job.id,
        public_id=job.public_id,
        status=job.status,
        progress=job.progress,
        message=job.progress_message,
        metadata={
            "execution_mode": job.execution_mode,
            "queue_name": job.queue_name,
            "provider_job_id": (
                job.provider_job_id
            ),
        },
    )

    return JobProgressCacheResponse(
        found=True,
        value=JobProgressCacheValue(
            **value.model_dump()
        ),
        ttl_seconds=None,
    )