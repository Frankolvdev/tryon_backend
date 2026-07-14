from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.schemas.feature_flag import PublicFeatureFlagsResponse
from app.services.feature_flag_service import feature_flag_service

router = APIRouter()


@router.get("/public", response_model=PublicFeatureFlagsResponse)
def get_public_feature_flags(
    db: Session = Depends(get_db),
):
    return PublicFeatureFlagsResponse(
        flags=feature_flag_service.list_public_flags(db),
    )