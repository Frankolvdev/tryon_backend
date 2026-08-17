import zipfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.model_generation_asset import ModelGenerationAssetCreate, ModelGenerationAssetUpdate
from app.services.model_generation_asset_service import model_generation_asset_service
from app.services.model_generation_bundle_service import model_generation_bundle_service

router = APIRouter(prefix="/tools-generation/model-assets")


def bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/storage-options")
def storage_options(db: Session = Depends(get_db)):
    return model_generation_asset_service.storage_options(db)


@router.get("")
def list_assets(tool_key: str | None = None, db: Session = Depends(get_db)):
    try:
        rows = model_generation_asset_service.list(db, tool_key=tool_key)
        return {"items": [model_generation_asset_service.response(db, row) for row in rows], "total": len(rows)}
    except ValueError as exc:
        raise bad_request(exc)


@router.post("")
def create_asset(data: ModelGenerationAssetCreate, db: Session = Depends(get_db)):
    try:
        return model_generation_asset_service.response(db, model_generation_asset_service.create(db, data))
    except ValueError as exc:
        raise bad_request(exc)


@router.patch("/{asset_id}")
def update_asset(asset_id: int, data: ModelGenerationAssetUpdate, db: Session = Depends(get_db)):
    try:
        return model_generation_asset_service.response(db, model_generation_asset_service.update(db, asset_id, data))
    except ValueError as exc:
        raise bad_request(exc)


@router.post("/{asset_id}/media")
def upload_media(
    asset_id: int,
    kind: str = Form(...),
    media: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        row = model_generation_asset_service.upload_media(
            db,
            asset_id,
            kind=kind,
            content=media.file.read(),
            filename=media.filename or f"{kind}.bin",
            content_type=media.content_type,
        )
        return model_generation_asset_service.response(db, row)
    except ValueError as exc:
        raise bad_request(exc)


@router.delete("/{asset_id}", status_code=204)
def delete_asset(asset_id: int, db: Session = Depends(get_db)):
    try:
        model_generation_asset_service.delete(db, asset_id)
        return Response(status_code=204)
    except ValueError as exc:
        raise bad_request(exc)


@router.get("/bundle/export/zip")
def export_bundle(db: Session = Depends(get_db)):
    content = model_generation_bundle_service.export_zip(db)
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="models-ia-assets.zip"'},
    )


@router.post("/bundle/import/zip")
def import_bundle(
    archive: UploadFile = File(...),
    target: str = Form("auto"),
    db: Session = Depends(get_db),
):
    try:
        return model_generation_bundle_service.import_zip(db, archive.file.read(), target=target)
    except (ValueError, KeyError, zipfile.BadZipFile) as exc:  # type: ignore[name-defined]
        raise bad_request(exc)
