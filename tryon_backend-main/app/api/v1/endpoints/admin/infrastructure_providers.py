from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.schemas.infrastructure_provider import ModalProviderConfig, ModalProviderResponse, ProviderActionResponse
from app.services.infrastructure_provider_service import infrastructure_provider_service

router = APIRouter(prefix="/infrastructure-providers", dependencies=[Depends(admin_guard)])


def _response(config: ModalProviderConfig) -> ModalProviderResponse:
    return ModalProviderResponse(
        **{**config.model_dump(), "token_secret": ""},
        token_secret_configured=bool(config.token_secret),
    )


@router.get("/modal", response_model=ModalProviderResponse)
def read_modal(db: Session = Depends(get_db)):
    return _response(infrastructure_provider_service.get_modal(db))


@router.put("/modal", response_model=ModalProviderResponse)
def update_modal(payload: ModalProviderConfig, db: Session = Depends(get_db)):
    return _response(infrastructure_provider_service.save_modal(db, payload))


@router.post("/modal/test", response_model=ProviderActionResponse)
def test_modal(db: Session = Depends(get_db)):
    return infrastructure_provider_service.test_modal(db)


@router.post("/modal/volume", response_model=ProviderActionResponse)
def ensure_modal_volume(db: Session = Depends(get_db)):
    return infrastructure_provider_service.ensure_volume(db)
