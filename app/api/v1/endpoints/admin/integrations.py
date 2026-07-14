from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.common.enums import IntegrationProvider
from app.models.user import User
from app.schemas.integration import (
    IntegrationConfigResponse,
    IntegrationConfigUpdate,
    IntegrationEventResponse,
    IntegrationHealthResponse,
    IntegrationSeedResponse,
)
from app.services.audit_service import audit_service
from app.services.integration_service import integration_service

router = APIRouter()


@router.post("/integrations/seed-defaults", response_model=IntegrationSeedResponse)
def seed_default_integrations(
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = integration_service.seed_defaults(db)

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_integrations_seeded",
        entity_type="integration_configs",
        entity_id=None,
        description="Admin seeded default integration configs.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return result


@router.get("/integrations", response_model=list[IntegrationConfigResponse])
def list_integrations(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return integration_service.list_configs(db)


@router.get("/integrations/{provider}", response_model=IntegrationConfigResponse)
def get_integration(
    provider: IntegrationProvider,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return integration_service.get_config_response(db, provider)


@router.patch("/integrations/{provider}", response_model=IntegrationConfigResponse)
def update_integration(
    provider: IntegrationProvider,
    data: IntegrationConfigUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = integration_service.update_config(
        db=db,
        provider=provider,
        data=data,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_integration_updated",
        entity_type="integration_config",
        entity_id=provider.value,
        description=f"Admin updated integration config {provider.value}.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return result


@router.post("/integrations/{provider}/health", response_model=IntegrationHealthResponse)
def check_integration_health(
    provider: IntegrationProvider,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return integration_service.health_check(db, provider)


@router.get("/integration-events", response_model=list[IntegrationEventResponse])
def list_integration_events(
    provider: IntegrationProvider | None = Query(default=None),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
):
    return integration_service.list_events(
        db=db,
        provider=provider,
        skip=skip,
        limit=limit,
    )