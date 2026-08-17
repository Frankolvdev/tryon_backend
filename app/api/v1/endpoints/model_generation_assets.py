from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.model_generation_asset_service import model_generation_asset_service

router = APIRouter()


@router.get("")
def list_assets(tool_key: str | None = None, db: Session = Depends(get_db)):
    try:
        rows = model_generation_asset_service.list(db, tool_key=tool_key, active_only=True)
        return {"items": [model_generation_asset_service.response(db, row) for row in rows], "total": len(rows)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
