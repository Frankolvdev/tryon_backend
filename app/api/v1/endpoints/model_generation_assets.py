import hmac
import os

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.model_generation_asset import ModelGenerationAsset
from app.models.storage_file import StorageFile
from app.services.model_generation_asset_service import model_generation_asset_service
from app.services.storage_service import storage_service

router = APIRouter()


def _require_appweb_internal_key(value: str | None) -> None:
    expected = os.getenv("APPWEB_INTERNAL_KEY", "").strip()
    if not expected or not value or not hmac.compare_digest(value, expected):
        raise HTTPException(status_code=404, detail="Not found.")


@router.get("/private/facial-structures/count")
def private_face_count(
    x_appweb_internal_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    _require_appweb_internal_key(x_appweb_internal_key)
    total = db.query(ModelGenerationAsset).filter(
        ModelGenerationAsset.tool_key == "facial_structures",
        ModelGenerationAsset.is_active.is_(True),
        ModelGenerationAsset.poster_storage_file_id.isnot(None),
    ).count()
    return {"total": total}


@router.get("/private/facial-structures/reference")
def private_face_reference(
    index: int = Query(ge=0),
    x_appweb_internal_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    _require_appweb_internal_key(x_appweb_internal_key)
    row = db.query(ModelGenerationAsset).filter(
        ModelGenerationAsset.tool_key == "facial_structures",
        ModelGenerationAsset.is_active.is_(True),
        ModelGenerationAsset.poster_storage_file_id.isnot(None),
    ).order_by(ModelGenerationAsset.id.asc()).offset(index).limit(1).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Face reference not found.")
    stored = db.get(StorageFile, row.poster_storage_file_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Face reference file not found.")
    content = storage_service.read_bytes(db, storage_file=stored)
    return Response(
        content=content,
        media_type=stored.content_type or "image/webp",
        headers={
            "Cache-Control": "no-store, private",
            "Content-Disposition": 'inline; filename="face-reference.webp"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("")
def list_assets(
    tool_key: str | None = None,
    tool_keys: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        if tool_key == "facial_structures" or (tool_keys and "facial_structures" in {item.strip() for item in tool_keys.split(",")}):
            raise ValueError("Unsupported tool key.")
        requested_tools = (
            [item.strip() for item in tool_keys.split(",") if item.strip()]
            if tool_keys
            else None
        )
        rows = model_generation_asset_service.list(
            db,
            tool_key=tool_key,
            tool_keys=requested_tools,
            active_only=True,
        )
        return {"items": [model_generation_asset_service.response(db, row) for row in rows], "total": len(rows)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
