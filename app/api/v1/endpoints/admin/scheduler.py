from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.scheduler import (
    ManualRunRequest,
    ScheduledJobCreate,
    ScheduledJobResponse,
    ScheduledJobRunResponse,
    ScheduledJobUpdate,
)
from app.services.scheduler_service import scheduler_service

router = APIRouter()


@router.get("/scheduled-jobs", response_model=list[ScheduledJobResponse])
def list_scheduled_jobs(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
):
    return scheduler_service.list_jobs(db=db, skip=skip, limit=limit)


@router.post("/scheduled-jobs", response_model=ScheduledJobResponse)
def create_scheduled_job(
    data: ScheduledJobCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return scheduler_service.create_job(db=db, data=data)


@router.patch("/scheduled-jobs/{job_id}", response_model=ScheduledJobResponse)
def update_scheduled_job(
    job_id: int,
    data: ScheduledJobUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return scheduler_service.update_job(db=db, job_id=job_id, data=data)


@router.get(
    "/scheduled-jobs/{job_id}/runs",
    response_model=list[ScheduledJobRunResponse],
)
def list_scheduled_job_runs(
    job_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
):
    return scheduler_service.list_runs(
        db=db,
        job_id=job_id,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/scheduled-jobs/{job_id}/run",
    response_model=ScheduledJobRunResponse,
)
def run_scheduled_job_manually(
    job_id: int,
    data: ManualRunRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return scheduler_service.run_job_manually(
        db=db,
        job_id=job_id,
        note=data.note,
    )