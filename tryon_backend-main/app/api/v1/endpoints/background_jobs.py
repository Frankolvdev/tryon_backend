from fastapi import (
    APIRouter,
    Depends,
    Query,
    Response,
)
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.auth_guard import auth_guard
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
    BackgroundJobDependencyListResponse,
    BackgroundJobDetailResponse,
    BackgroundJobListResponse,
    BackgroundJobResponse,
    UserBackgroundJobCreate,
)
from app.services.background_job_dispatch_service import (
    background_job_dispatch_service,
)
from app.services.background_job_service import (
    background_job_service,
)

router = APIRouter()


@router.post(
    "",
    response_model=BackgroundJobResponse,
    status_code=201,
)
def create_background_job(
    data: UserBackgroundJobCreate,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    result, created = (
        background_job_dispatch_service
        .create_user_job(
            db,
            user_id=current_user.id,
            data=data,
        )
    )

    if not created:
        response.status_code = 200
        response.headers[
            "X-Idempotent-Replay"
        ] = "true"

    return result


@router.get(
    "",
    response_model=BackgroundJobListResponse,
)
def list_my_background_jobs(
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
        le=200,
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return background_job_service.list_jobs(
        db,
        user_id=current_user.id,
        queue_name=(
            queue_name.value
            if queue_name
            else None
        ),
        job_type=job_type,
        status=status.value if status else None,
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
    "/{job_id}",
    response_model=BackgroundJobDetailResponse,
)
def get_my_background_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return background_job_service.get_detail(
        db,
        job_id=job_id,
        user_id=current_user.id,
    )


@router.get(
    "/{job_id}/attempts",
    response_model=BackgroundJobAttemptListResponse,
)
def list_my_background_job_attempts(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return background_job_service.list_attempts(
        db,
        job_id=job_id,
        user_id=current_user.id,
    )


@router.get(
    "/{job_id}/dependencies",
    response_model=(
        BackgroundJobDependencyListResponse
    ),
)
def list_my_background_job_dependencies(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return background_job_service.list_dependencies(
        db,
        job_id=job_id,
        user_id=current_user.id,
    )


@router.post(
    "/{job_id}/cancel",
    response_model=BackgroundJobCancelResponse,
)
def cancel_my_background_job(
    job_id: int,
    data: BackgroundJobCancelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return background_job_dispatch_service.cancel_job(
        db,
        job_id=job_id,
        reason=data.reason,
        user_id=current_user.id,
    )