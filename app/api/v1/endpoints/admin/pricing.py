from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.pricing import (
    CommercialPricePreviewRequest,
    CommercialPricePreviewResponse,
    CommercialSettingsResponse,
    CommercialSettingsUpdate,
    PricingRuleCreate,
    PricingRuleResponse,
    PricingRuleUpdate,
)
from app.schemas.simulated_engine import CommercialRepriceResponse
from app.services.audit_service import audit_service
from app.services.pricing_service import pricing_service

router = APIRouter()


@router.get("/commercial-settings", response_model=CommercialSettingsResponse)
def get_commercial_settings(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return pricing_service.get_commercial_settings(db)


@router.patch("/commercial-settings", response_model=CommercialSettingsResponse)
def update_commercial_settings(
    data: CommercialSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = pricing_service.update_commercial_settings(db, data)
    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_commercial_settings_updated",
        entity_type="commercial_settings",
        entity_id=None,
        description=(
            f"Commercial settings updated: 1 token = {result.token_value_usd} "
            f"{result.currency}."
        ),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return result


@router.post("/commercial-price-preview", response_model=CommercialPricePreviewResponse)
def preview_commercial_price(
    data: CommercialPricePreviewRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return pricing_service.preview(
        db,
        average_execution_cost_usd=data.average_execution_cost_usd,
        desired_profit_percent=data.desired_profit_percent,
    )


@router.get("/pricing-rules", response_model=list[PricingRuleResponse])
def list_pricing_rules(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return pricing_service.list_rules(db)


@router.post("/pricing-rules", response_model=PricingRuleResponse)
def create_pricing_rule(
    data: PricingRuleCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return pricing_service.create_rule(db=db, data=data)


@router.patch("/pricing-rules/{rule_id}", response_model=PricingRuleResponse)
def update_pricing_rule(
    rule_id: int,
    data: PricingRuleUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return pricing_service.update_rule(db=db, rule_id=rule_id, data=data)


@router.post("/commercial-reprice", response_model=CommercialRepriceResponse)
def reprice_commercial_catalog(request: Request, db: Session = Depends(get_db), current_admin: User = Depends(admin_guard)):
    result = pricing_service.reprice_catalog(db)
    audit_service.create_log(db, actor_user_id=current_admin.id, action="admin_commercial_catalog_repriced", entity_type="commercial_catalog", entity_id=None, description=f"Repriced {result['plans_updated']} plans and {result['packages_updated']} token packages.", ip_address=request.client.host if request.client else None, user_agent=request.headers.get("user-agent"))
    return CommercialRepriceResponse(**result, message="Commercial catalog repriced successfully.")
