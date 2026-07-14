from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.runpod_external import (
    ExternalAiJobResponse,
    RunPodCancelRequest,
    RunPodCancelResponse,
    RunPodStatusResponse,
    RunPodSubmitRequest,
    RunPodSubmitResponse,
)
from app.services.external_ai_job_service import external_ai_job_service

router = APIRouter()


@router.get("/external-ai-jobs", response_model=list[ExternalAiJobResponse])
def list_external_ai_jobs(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
):
    return external_ai_job_service.list_jobs(db=db, skip=skip, limit=limit)


@router.post("/runpod/jobs", response_model=RunPodSubmitResponse)
def submit_runpod_job(
    data: RunPodSubmitRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return external_ai_job_service.submit_runpod_job(db=db, data=data)


@router.post("/runpod/jobs/{external_ai_job_id}/status", response_model=RunPodStatusResponse)
def refresh_runpod_job_status(
    external_ai_job_id: int,
    endpoint_id: str,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return external_ai_job_service.refresh_runpod_status(
        db=db,
        external_ai_job_id=external_ai_job_id,
        endpoint_id=endpoint_id,
    )


@router.post("/runpod/jobs/{external_ai_job_id}/cancel", response_model=RunPodCancelResponse)
def cancel_runpod_job(
    external_ai_job_id: int,
    data: RunPodCancelRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return external_ai_job_service.cancel_runpod_job(
        db=db,
        external_ai_job_id=external_ai_job_id,
        endpoint_id=data.endpoint_id,
    )