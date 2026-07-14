from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.tryon import TryOnJobAdminUpdate, TryOnJobResponse
from app.services.tryon_service import tryon_service

router = APIRouter()


@router.get("/tryon-jobs", response_model=list[TryOnJobResponse])
def list_tryon_jobs_admin(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    return tryon_service.admin_list_jobs(
        db=db,
        skip=skip,
        limit=limit,
    )


@router.get("/tryon-jobs/{job_id}", response_model=TryOnJobResponse)
def get_tryon_job_admin(
    job_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return tryon_service.admin_get_job(
        db=db,
        job_id=job_id,
    )


@router.patch("/tryon-jobs/{job_id}", response_model=TryOnJobResponse)
def update_tryon_job_admin(
    job_id: int,
    data: TryOnJobAdminUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return tryon_service.admin_update_job(
        db=db,
        job_id=job_id,
        data=data,
    )