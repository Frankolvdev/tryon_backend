from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.ancestry_media_asset import (
    AncestryAssetCreate, AncestryAssetListResponse, AncestryAssetResponse,
    AncestryAssetUpdate, AncestryStorageOptionsResponse,
)
from app.services.ancestry_media_asset_service import ancestry_media_asset_service

router = APIRouter(prefix="/tools-generation/ancestry-assets")


def _fail(error: Exception):
    if isinstance(error, LookupError):
        raise HTTPException(status_code=404, detail=str(error)) from error
    raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/storage-options", response_model=AncestryStorageOptionsResponse)
def storage_options(db: Session = Depends(get_db), current_admin: User = Depends(admin_guard)):
    return ancestry_media_asset_service.storage_options(db)


@router.get("", response_model=AncestryAssetListResponse)
def list_assets(db: Session = Depends(get_db), current_admin: User = Depends(admin_guard)):
    rows = ancestry_media_asset_service.list(db)
    return {"items": [ancestry_media_asset_service.response(db, row) for row in rows], "total": len(rows)}


@router.post("", response_model=AncestryAssetResponse, status_code=status.HTTP_201_CREATED)
def create_asset(data: AncestryAssetCreate, db: Session = Depends(get_db), current_admin: User = Depends(admin_guard)):
    try:
        return ancestry_media_asset_service.response(db, ancestry_media_asset_service.create(db, data))
    except Exception as error: _fail(error)


@router.patch("/{asset_id}", response_model=AncestryAssetResponse)
def update_asset(asset_id: int, data: AncestryAssetUpdate, db: Session = Depends(get_db), current_admin: User = Depends(admin_guard)):
    try:
        return ancestry_media_asset_service.response(db, ancestry_media_asset_service.update(db, asset_id, data))
    except Exception as error: _fail(error)


@router.post("/{asset_id}/media", response_model=AncestryAssetResponse)
def upload_media(
    asset_id: int,
    kind: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    try:
        content = file.file.read()
        row = ancestry_media_asset_service.upload_media(
            db, asset_id, kind=kind, content=content,
            filename=file.filename or ("poster.webp" if kind == "poster" else "video.mp4"),
            content_type=file.content_type,
        )
        return ancestry_media_asset_service.response(db, row)
    except Exception as error: _fail(error)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(asset_id: int, db: Session = Depends(get_db), current_admin: User = Depends(admin_guard)):
    try:
        ancestry_media_asset_service.delete(db, asset_id)
        return Response(status_code=204)
    except Exception as error: _fail(error)


@router.get("/export/zip")
def export_zip(db: Session = Depends(get_db), current_admin: User = Depends(admin_guard)):
    try:
        content = ancestry_media_asset_service.export_zip(db)
        return Response(content=content, media_type="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="ancestry-assets.zip"'})
    except Exception as error: _fail(error)


@router.post("/import/zip")
def import_zip(
    archive: UploadFile = File(...),
    target: str = Form("auto"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    try:
        if not str(archive.filename or "").lower().endswith(".zip"):
            raise ValueError("Select a .zip file.")
        return ancestry_media_asset_service.import_zip(db, archive.file.read(), target=target)
    except Exception as error: _fail(error)
