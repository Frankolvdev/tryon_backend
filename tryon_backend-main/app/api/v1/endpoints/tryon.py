from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.auth_guard import auth_guard
from app.common.enums import QualityMode, TryOnItemType
from app.models.user import User
from app.schemas.tryon import TryOnCreateResponse, TryOnJobResponse
from app.services.tryon_service import tryon_service

router = APIRouter()


@router.post("/", response_model=TryOnCreateResponse)
def create_tryon_job(
    person_image: UploadFile = File(...),
    item_image: UploadFile = File(...),
    item_type: TryOnItemType = Form(default=TryOnItemType.CLOTHING),
    quality_mode: QualityMode = Form(default=QualityMode.STANDARD),
    prompt: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return tryon_service.create_tryon_job(
        db=db,
        user=current_user,
        person_image=person_image,
        item_image=item_image,
        item_type=item_type,
        quality_mode=quality_mode,
        prompt=prompt,
    )


@router.get("/", response_model=list[TryOnJobResponse])
def list_my_tryon_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    return tryon_service.list_my_jobs(
        db=db,
        user=current_user,
        skip=skip,
        limit=limit,
    )


@router.get("/{job_id}", response_model=TryOnJobResponse)
def get_my_tryon_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_guard),
):
    return tryon_service.get_my_job(
        db=db,
        user=current_user,
        job_id=job_id,
    )