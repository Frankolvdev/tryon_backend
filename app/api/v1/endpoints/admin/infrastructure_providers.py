from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.schemas.infrastructure_provider import ModalProviderConfig, ModalProviderResponse, RunPodProviderConfig, RunPodProviderResponse, BeamProviderConfig, BeamProviderResponse, ProviderActionResponse
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


def _runpod_response(config: RunPodProviderConfig) -> RunPodProviderResponse:
    return RunPodProviderResponse(
        **{**config.model_dump(), "api_key": "", "s3_secret_key": "", "ghcr_token": ""},
        api_key_configured=bool(config.api_key),
        s3_secret_key_configured=bool(config.s3_secret_key),
        ghcr_token_configured=bool(config.ghcr_token),
    )

@router.get("/runpod", response_model=RunPodProviderResponse)
def read_runpod(db: Session = Depends(get_db)): return _runpod_response(infrastructure_provider_service.get_runpod(db))
@router.put("/runpod", response_model=RunPodProviderResponse)
def update_runpod(payload: RunPodProviderConfig, db: Session = Depends(get_db)): return _runpod_response(infrastructure_provider_service.save_runpod(db,payload))
@router.post("/runpod/test", response_model=ProviderActionResponse)
def test_runpod(db: Session = Depends(get_db)): return infrastructure_provider_service.test_runpod(db)
@router.post("/runpod/volume", response_model=ProviderActionResponse)
def ensure_runpod_volume(db: Session = Depends(get_db)): return infrastructure_provider_service.ensure_runpod_volume(db)

def _beam_response(config: BeamProviderConfig) -> BeamProviderResponse:
    return BeamProviderResponse(**{**config.model_dump(), "api_key": ""}, api_key_configured=bool(config.api_key))
@router.get("/beam", response_model=BeamProviderResponse)
def read_beam(db: Session = Depends(get_db)): return _beam_response(infrastructure_provider_service.get_beam(db))
@router.put("/beam", response_model=BeamProviderResponse)
def update_beam(payload: BeamProviderConfig, db: Session = Depends(get_db)): return _beam_response(infrastructure_provider_service.save_beam(db,payload))
@router.post("/beam/test", response_model=ProviderActionResponse)
def test_beam(db: Session = Depends(get_db)): return infrastructure_provider_service.test_beam(db)
@router.post("/beam/volume", response_model=ProviderActionResponse)
def ensure_beam_volume(db: Session = Depends(get_db)): return infrastructure_provider_service.ensure_beam_volume(db)
