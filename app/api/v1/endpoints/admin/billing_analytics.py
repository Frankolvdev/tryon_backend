from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.billing_analytics import (
    BillingDashboardResponse,
    BillingMaintenanceOptions,
    BillingMaintenanceResponse,
    BillingRevenueMetricsResponse,
    BillingSubscriptionMetricsResponse,
    BillingTokenMetricsResponse,
)
from app.services.audit_service import audit_service
from app.services.billing_analytics_service import (
    billing_analytics_service,
)
from app.services.billing_maintenance_service import (
    billing_maintenance_service,
)

router = APIRouter()


@router.get(
    "/billing-analytics/dashboard",
    response_model=BillingDashboardResponse,
)
def get_billing_dashboard(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    currency: str = Query(
        default="USD",
        min_length=3,
        max_length=3,
    ),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return billing_analytics_service.dashboard(
        db,
        start=start,
        end=end,
        currency=currency,
    )


@router.get(
    "/billing-analytics/revenue",
    response_model=BillingRevenueMetricsResponse,
)
def get_billing_revenue_metrics(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    currency: str = Query(
        default="USD",
        min_length=3,
        max_length=3,
    ),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return billing_analytics_service.revenue_metrics(
        db,
        start=start,
        end=end,
        currency=currency,
    )


@router.get(
    "/billing-analytics/subscriptions",
    response_model=BillingSubscriptionMetricsResponse,
)
def get_billing_subscription_metrics(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    currency: str = Query(
        default="USD",
        min_length=3,
        max_length=3,
    ),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return billing_analytics_service.subscription_metrics(
        db,
        start=start,
        end=end,
        currency=currency,
    )


@router.get(
    "/billing-analytics/tokens",
    response_model=BillingTokenMetricsResponse,
)
def get_billing_token_metrics(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return billing_analytics_service.token_metrics(
        db,
        start=start,
        end=end,
    )


@router.post(
    "/billing-maintenance/run",
    response_model=BillingMaintenanceResponse,
)
def run_billing_maintenance(
    data: BillingMaintenanceOptions,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = billing_maintenance_service.run(
        db,
        options=data,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_billing_maintenance_executed",
        entity_type="billing_maintenance",
        entity_id=None,
        description=(
            "Executed complete billing maintenance. "
            f"Processed: {result.total_processed}; "
            f"failed: {result.total_failed}."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get("user-agent"),
    )

    return result