from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.auth_guard import auth_guard
from app.models.user import User
from app.schemas.ancestry_media_asset import AncestryAssetListResponse
from app.services.ancestry_media_asset_service import ancestry_media_asset_service

router = APIRouter()


@router.get("", response_model=AncestryAssetListResponse)
def list_active_assets(db: Session = Depends(get_db), current_user: User = Depends(auth_guard)):
    rows = ancestry_media_asset_service.list(db, active_only=True)
    return {"items": [ancestry_media_asset_service.response(db, row) for row in rows], "total": len(rows)}
