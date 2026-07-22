from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.runtime_builder_config import RuntimeBuilderConfig
from app.schemas.runtime_builder import (
    RuntimeBuilderConfigResponse,
    RuntimeBuilderConfigUpdate,
    RuntimeGeneratedFilesResponse,
    RuntimeValidationResponse,
)
from app.services.runtime_builder_service import RuntimeBuilderService

router = APIRouter(prefix="/runtime-builder", dependencies=[Depends(admin_guard)])


def get_or_create(db: Session) -> RuntimeBuilderConfig:
    config = db.query(RuntimeBuilderConfig).order_by(RuntimeBuilderConfig.id.asc()).first()
    if config is None:
        config = RuntimeBuilderConfig()
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


@router.get("/config", response_model=RuntimeBuilderConfigResponse)
def read_config(db: Session = Depends(get_db)):
    return get_or_create(db)


@router.put("/config", response_model=RuntimeBuilderConfigResponse)
def update_config(payload: RuntimeBuilderConfigUpdate, db: Session = Depends(get_db)):
    config = get_or_create(db)
    for field, value in payload.model_dump().items():
        setattr(config, field, value)
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@router.post("/validate", response_model=RuntimeValidationResponse)
def validate_config(db: Session = Depends(get_db)):
    return RuntimeBuilderService.validate(get_or_create(db))


@router.post("/generate", response_model=RuntimeGeneratedFilesResponse)
def generate_files(db: Session = Depends(get_db)):
    config = get_or_create(db)
    validation = RuntimeBuilderService.validate(config)
    return RuntimeBuilderService.generate(config)
