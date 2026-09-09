from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.schemas.system_setting import (
    PublicFrontendConfigResponse,
    PublicSystemSettingResponse,
)
from app.schemas.system_status import PublicSystemStatusResponse
from app.services.system_setting_service import system_setting_service
from app.services.branding_service import branding_service
from app.services.system_status_service import system_status_service

router = APIRouter()


@router.get("/status", response_model=PublicSystemStatusResponse)
def get_system_status(
    db: Session = Depends(get_db),
):
    status = system_status_service.get_public_status(db)

    return PublicSystemStatusResponse(
        maintenance_mode=status.maintenance_mode,
        registration_enabled=status.registration_enabled,
        tryon_enabled=status.tryon_enabled,
        public_message=status.public_message,
    )


@router.get("/settings/public", response_model=list[PublicSystemSettingResponse])
def get_public_system_settings(
    db: Session = Depends(get_db),
):
    return system_setting_service.list_public_settings(db)


@router.get("/config", response_model=PublicFrontendConfigResponse)
def get_public_frontend_config(
    db: Session = Depends(get_db),
):
    return system_setting_service.get_public_frontend_config(db)

@router.get("/branding")
def get_public_branding(db: Session = Depends(get_db)):
    response = branding_service.response(db)
    # Provider is an administrative implementation detail; public clients only
    # need stable, cacheable URLs.
    response.pop("active_storage_provider", None)
    return response


@router.get("/branding/assets/{asset_key}")
def get_public_branding_asset(asset_key: str, db: Session = Depends(get_db)):
    if asset_key not in {"logo-small", "logo-medium", "logo-large", "favicon"}:
        raise HTTPException(status_code=404, detail="Branding asset not found.")
    try:
        content, content_type, etag = branding_service.asset(db, asset_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "ETag": f'"{etag}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
