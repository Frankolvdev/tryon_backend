from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.common.responses import SuccessResponse
from app.models.user import User
from app.schemas.pricing_simulator import PricingSimulatorRequest, PricingSimulatorResponse
from app.services.pricing_simulator_service import pricing_simulator_service
from app.schemas.pricing import (
    CommercialPricePreviewRequest,
    CommercialPricePreviewResponse,
    CommercialSettingsResponse,
    CommercialSettingsUpdate,
    ExecutionBillingPolicy,
    ExecutionBillingPolicyUpdate,
    PricingRuleCreate,
    PricingRuleResponse,
    PricingRuleUpdate,
)
from app.schemas.simulated_engine import CommercialRepriceResponse
from app.schemas.provider_pricing import ProviderGpuPriceResponse, ProviderGpuPriceUpsert, AppliedPricingRuleResponse
from app.schemas.financial_protection import FinancialProtectionReport, ProtectedCommercialPrice
from app.services.audit_service import audit_service
from app.services.pricing_service import pricing_service
from app.services.provider_pricing_service import provider_pricing_service
from app.services.financial_protection_service import financial_protection_service

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




@router.get("/execution-billing-policy", response_model=ExecutionBillingPolicy)
def get_execution_billing_policy(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return pricing_service.get_execution_billing_policy(db)


@router.patch("/execution-billing-policy", response_model=ExecutionBillingPolicy)
def update_execution_billing_policy(
    data: ExecutionBillingPolicyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = pricing_service.update_execution_billing_policy(db, data)
    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_execution_billing_policy_updated",
        entity_type="execution_billing_policy",
        entity_id=None,
        description="Execution billing policy updated.",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return result




@router.get("/financial-protection", response_model=FinancialProtectionReport)
def get_financial_protection(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return financial_protection_service.report(db)


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
        desired_profit_usd=data.desired_profit_usd,
        desired_profit_per_token_usd=data.desired_profit_per_token_usd,
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


@router.delete("/pricing-rules/{rule_id}", response_model=SuccessResponse)
def delete_pricing_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    pricing_service.delete_rule(db=db, rule_id=rule_id)
    return SuccessResponse(message="Pricing rule deleted successfully.")


@router.post("/commercial-reprice", response_model=CommercialRepriceResponse)
def reprice_commercial_catalog(request: Request, db: Session = Depends(get_db), current_admin: User = Depends(admin_guard)):
    result = pricing_service.reprice_catalog(db)
    audit_service.create_log(db, actor_user_id=current_admin.id, action="admin_commercial_catalog_repriced", entity_type="commercial_catalog", entity_id=None, description=f"Repriced {result['plans_updated']} plans and {result['packages_updated']} token packages.", ip_address=request.client.host if request.client else None, user_agent=request.headers.get("user-agent"))
    return CommercialRepriceResponse(**result, message="Commercial catalog repriced successfully.")


@router.get("/provider-gpu-prices", response_model=list[ProviderGpuPriceResponse])
def list_provider_gpu_prices(
    provider: str | None = None,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return provider_pricing_service.list_prices(db, provider=provider)


@router.put("/provider-gpu-prices", response_model=ProviderGpuPriceResponse)
def upsert_provider_gpu_price(
    data: ProviderGpuPriceUpsert,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return provider_pricing_service.upsert(db, data)


@router.delete("/provider-gpu-prices/{price_id}", response_model=SuccessResponse)
def delete_provider_gpu_price(
    price_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    provider_pricing_service.delete(db, price_id)
    return SuccessResponse(message="Provider GPU price deleted successfully.")


@router.get("/applied-pricing-rules", response_model=list[AppliedPricingRuleResponse])
def list_applied_pricing_rules(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return pricing_service.list_applied_rules(db)


@router.post("/pricing-simulator", response_model=PricingSimulatorResponse)
def simulate_pricing(
    data: PricingSimulatorRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return pricing_simulator_service.simulate(db, data)
