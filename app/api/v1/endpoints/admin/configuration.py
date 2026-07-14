from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.services.configuration_validation_service import configuration_validation_service

router = APIRouter()


@router.get("/configuration/validate")
def validate_configuration(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return configuration_validation_service.validate(db)