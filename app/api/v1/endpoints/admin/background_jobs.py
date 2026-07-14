from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
    Response,
)
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.common.job_enums import (
    JobExecutionMode,
    JobQueueName,
    JobStatus,
)
from app.models.user import User
from app.schemas.background_job import (
    BackgroundJobAttemptListResponse,
    BackgroundJobCancelRequest,
    BackgroundJobCancelResponse,
    BackgroundJobCreate,
    BackgroundJobDependencyListResponse,
    BackgroundJobDetailResponse,
    BackgroundJobListResponse,
    BackgroundJobProgressUpdate,
    BackgroundJobResponse,
    BackgroundJobRetryRequest,
    BackgroundJobRetryResponse,
)
from app.services.audit_service import audit_service
from app.services.background_job_dispatch_service import (
    background_job_dispatch_service,
)
from app.services.background_job_handler_service import (
    BackgroundJobHandlerListResponse,
    background_job_handler_service,
)
from app.services.background_job_service import (
    background_job_service,
)


router = APIRouter()


@router.get(
    "/background-jobs/handlers",
    response_model=(
        BackgroundJobHandlerListResponse
    ),
)
def list_background_job_handlers(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return (
        background_job_handler_service
        .list_handlers(db)
    )


@router.post(
    "/background-jobs",
    response_model=BackgroundJobResponse,
    status_code=201,
)
def create_background_job(
    data: BackgroundJobCreate,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result, created = (
        background_job_dispatch_service.create_job(
            db,
            data=data,
        )
    )

    if not created:
        response.status_code = 200
        response.headers[
            "X-Idempotent-Replay"
        ] = "true"

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_background_job_created",
        entity_type="background_job",
        entity_id=str(result.id),
        description=(
            f"Created background job "
            f"{result.public_id} of type "
            f"{result.job_type}."
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


@router.get(
    "/background-jobs",
    response_model=BackgroundJobListResponse,
)
def list_background_jobs(
    user_id: int | None = Query(default=None),
    queue_name: JobQueueName | None = Query(
        default=None
    ),
    job_type: str | None = Query(default=None),
    status: JobStatus | None = Query(default=None),
    execution_mode: JobExecutionMode | None = Query(
        default=None
    ),
    search: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return background_job_service.list_jobs(
        db,
        user_id=user_id,
        queue_name=(
            queue_name.value
            if queue_name
            else None
        ),
        job_type=job_type,
        status=(
            status.value
            if status
            else None
        ),
        execution_mode=(
            execution_mode.value
            if execution_mode
            else None
        ),
        search=search,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/background-jobs/{job_id}",
    response_model=BackgroundJobDetailResponse,
)
def get_background_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return background_job_service.get_detail(
        db,
        job_id=job_id,
    )


@router.get(
    "/background-jobs/{job_id}/attempts",
    response_model=BackgroundJobAttemptListResponse,
)
def list_background_job_attempts(
    job_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return background_job_service.list_attempts(
        db,
        job_id=job_id,
    )


@router.get(
    "/background-jobs/{job_id}/dependencies",
    response_model=(
        BackgroundJobDependencyListResponse
    ),
)
def list_background_job_dependencies(
    job_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return background_job_service.list_dependencies(
        db,
        job_id=job_id,
    )


@router.post(
    "/background-jobs/{job_id}/cancel",
    response_model=BackgroundJobCancelResponse,
)
def cancel_background_job(
    job_id: int,
    data: BackgroundJobCancelRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = (
        background_job_dispatch_service.cancel_job(
            db,
            job_id=job_id,
            reason=data.reason,
        )
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_background_job_canceled",
        entity_type="background_job",
        entity_id=str(job_id),
        description=(
            f"Requested cancellation for "
            f"background job {job_id}."
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
    "/background-jobs/{job_id}/retry",
    response_model=BackgroundJobRetryResponse,
)
def retry_background_job(
    job_id: int,
    data: BackgroundJobRetryRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = (
        background_job_dispatch_service.retry_job(
            db,
            job_id=job_id,
            data=data,
        )
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_background_job_retried",
        entity_type="background_job",
        entity_id=str(job_id),
        description=(
            f"Queued background job {job_id} "
            "for manual retry."
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


@router.patch(
    "/background-jobs/{job_id}/progress",
    response_model=BackgroundJobResponse,
)
def update_background_job_progress(
    job_id: int,
    data: BackgroundJobProgressUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = background_job_service.update_progress(
        db,
        job_id=job_id,
        data=data,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action=(
            "admin_background_job_progress_updated"
        ),
        entity_type="background_job",
        entity_id=str(job_id),
        description=(
            f"Updated progress for background "
            f"job {job_id} to {data.progress}%."
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