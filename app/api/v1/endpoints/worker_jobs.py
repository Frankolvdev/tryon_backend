from fastapi import (
    APIRouter,
    Depends,
    Query,
)
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.worker_guard import (
    worker_guard,
)
from app.schemas.background_job import (
    BackgroundJobResponse,
)
from app.schemas.background_job_runtime import (
    BackgroundJobClaimRequest,
    BackgroundJobClaimResponse,
    BackgroundJobHeartbeatRequest,
    BackgroundJobHeartbeatResponse,
    BackgroundJobRecoveryResponse,
    BackgroundJobStartRequest,
)
from app.services.background_job_claim_service import (
    background_job_claim_service,
)


router = APIRouter(
    dependencies=[
        Depends(worker_guard),
    ]
)


@router.post(
    "/claim",
    response_model=BackgroundJobClaimResponse,
)
def claim_background_jobs(
    data: BackgroundJobClaimRequest,
    db: Session = Depends(get_db),
):
    return background_job_claim_service.claim(
        db,
        data=data,
    )


@router.post(
    "/{job_id}/start",
    response_model=BackgroundJobResponse,
)
def start_background_job(
    job_id: int,
    data: BackgroundJobStartRequest,
    db: Session = Depends(get_db),
):
    return background_job_claim_service.start(
        db,
        job_id=job_id,
        worker_name=data.worker_name,
        lease_token=data.lease_token,
    )


@router.post(
    "/{job_id}/heartbeat",
    response_model=BackgroundJobHeartbeatResponse,
)
def heartbeat_background_job(
    job_id: int,
    data: BackgroundJobHeartbeatRequest,
    db: Session = Depends(get_db),
):
    return background_job_claim_service.heartbeat(
        db,
        job_id=job_id,
        data=data,
    )


@router.post(
    "/recover-expired-leases",
    response_model=BackgroundJobRecoveryResponse,
)
def recover_expired_job_leases(
    limit: int = Query(
        default=100,
        ge=1,
        le=1000,
    ),
    db: Session = Depends(get_db),
):
    return (
        background_job_claim_service
        .recover_expired_leases(
            db,
            limit=limit,
        )
    )