from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.simulated_engine import SimulatedEngineSettingsResponse, SimulatedEngineSettingsUpdate, SimulatedEngineTestResponse
from app.services.audit_service import audit_service
from app.services.simulated_engine_service import simulated_engine_service
router = APIRouter()

@router.get("/simulated-engine/settings", response_model=SimulatedEngineSettingsResponse)
def get_settings(db: Session = Depends(get_db), current_admin: User = Depends(admin_guard)):
    return simulated_engine_service.get_settings(db)

@router.patch("/simulated-engine/settings", response_model=SimulatedEngineSettingsResponse)
def update_settings(data: SimulatedEngineSettingsUpdate, request: Request, db: Session = Depends(get_db), current_admin: User = Depends(admin_guard)):
    result = simulated_engine_service.update_settings(db, data)
    audit_service.create_log(db, actor_user_id=current_admin.id, action="admin_simulated_engine_updated", entity_type="simulated_engine", entity_id=None, description=f"Simulated engine updated. Mode: {result.execution_mode}.", ip_address=request.client.host if request.client else None, user_agent=request.headers.get("user-agent"))
    return result

@router.post("/simulated-engine/test", response_model=SimulatedEngineTestResponse)
def test_engine(db: Session = Depends(get_db), current_admin: User = Depends(admin_guard)):
    return simulated_engine_service.test(db)
