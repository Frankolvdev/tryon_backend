from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.pricing import (
    PricingRuleCreate,
    PricingRuleResponse,
    PricingRuleUpdate,
)
from app.services.pricing_service import pricing_service

router = APIRouter()


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
    return pricing_service.create_rule(
        db=db,
        data=data,
    )


@router.patch("/pricing-rules/{rule_id}", response_model=PricingRuleResponse)
def update_pricing_rule(
    rule_id: int,
    data: PricingRuleUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return pricing_service.update_rule(
        db=db,
        rule_id=rule_id,
        data=data,
    )