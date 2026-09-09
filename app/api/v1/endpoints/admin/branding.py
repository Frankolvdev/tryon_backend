from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.services.branding_service import branding_service

router = APIRouter(prefix="/branding")


class BrandingNameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@router.get("")
def get_branding(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return branding_service.response(db)


@router.post("/logo")
def upload_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    try:
        return branding_service.upload_logo(
            db,
            content=file.file.read(),
            filename=file.filename or "logo.png",
            content_type=file.content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/favicon")
def upload_favicon(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    try:
        return branding_service.upload_favicon(
            db,
            content=file.file.read(),
            filename=file.filename or "favicon.png",
            content_type=file.content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/favicon/use-auto")
def use_auto_favicon(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return branding_service.use_auto_favicon(db)


@router.post("/name")
def update_brand_name(
    data: BrandingNameRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    try:
        return branding_service.set_app_name(db, data.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
