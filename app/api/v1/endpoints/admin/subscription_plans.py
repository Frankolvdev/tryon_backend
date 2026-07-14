from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.common.billing_enums import BillingInterval
from app.common.responses import SuccessResponse
from app.models.user import User
from app.schemas.subscription_plan import (
    SubscriptionPlanCreate,
    SubscriptionPlanListResponse,
    SubscriptionPlanResponse,
    SubscriptionPlanSeedResponse,
    SubscriptionPlanSyncResponse,
    SubscriptionPlanUpdate,
)
from app.services.audit_service import audit_service
from app.services.subscription_plan_service import (
    subscription_plan_service,
)

router = APIRouter()


@router.get(
    "/subscription-plans",
    response_model=SubscriptionPlanListResponse,
)
def list_subscription_plans(
    search: str | None = Query(default=None),
    billing_interval: BillingInterval | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    is_public: bool | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return subscription_plan_service.list_admin_plans(
        db,
        search=search,
        billing_interval=billing_interval,
        is_active=is_active,
        is_public=is_public,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/subscription-plans/{plan_id}",
    response_model=SubscriptionPlanResponse,
)
def get_subscription_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return subscription_plan_service.get_response(
        db,
        plan_id,
    )


@router.post(
    "/subscription-plans",
    response_model=SubscriptionPlanResponse,
    status_code=201,
)
def create_subscription_plan(
    data: SubscriptionPlanCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = subscription_plan_service.create_plan(
        db,
        data=data,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_subscription_plan_created",
        entity_type="subscription_plan",
        entity_id=str(result.id),
        description=f"Created subscription plan {result.key}.",
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get("user-agent"),
    )

    return result


@router.patch(
    "/subscription-plans/{plan_id}",
    response_model=SubscriptionPlanResponse,
)
def update_subscription_plan(
    plan_id: int,
    data: SubscriptionPlanUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = subscription_plan_service.update_plan(
        db,
        plan_id=plan_id,
        data=data,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_subscription_plan_updated",
        entity_type="subscription_plan",
        entity_id=str(result.id),
        description=f"Updated subscription plan {result.key}.",
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get("user-agent"),
    )

    return result


@router.post(
    "/subscription-plans/{plan_id}/activate",
    response_model=SubscriptionPlanResponse,
)
def activate_subscription_plan(
    plan_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = subscription_plan_service.set_active(
        db,
        plan_id=plan_id,
        is_active=True,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_subscription_plan_activated",
        entity_type="subscription_plan",
        entity_id=str(result.id),
        description=f"Activated subscription plan {result.key}.",
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get("user-agent"),
    )

    return result


@router.post(
    "/subscription-plans/{plan_id}/deactivate",
    response_model=SubscriptionPlanResponse,
)
def deactivate_subscription_plan(
    plan_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = subscription_plan_service.set_active(
        db,
        plan_id=plan_id,
        is_active=False,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_subscription_plan_deactivated",
        entity_type="subscription_plan",
        entity_id=str(result.id),
        description=f"Deactivated subscription plan {result.key}.",
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get("user-agent"),
    )

    return result


@router.post(
    "/subscription-plans/{plan_id}/sync-stripe",
    response_model=SubscriptionPlanSyncResponse,
)
def sync_subscription_plan_with_stripe(
    plan_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = subscription_plan_service.sync_plan_with_stripe(
        db,
        plan_id=plan_id,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_subscription_plan_stripe_synced",
        entity_type="subscription_plan",
        entity_id=str(result.plan.id),
        description=(
            f"Synchronized subscription plan "
            f"{result.plan.key} with Stripe."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get("user-agent"),
    )

    return result


@router.delete(
    "/subscription-plans/{plan_id}",
    response_model=SuccessResponse,
)
def delete_subscription_plan(
    plan_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    plan = subscription_plan_service.get_plan(
        db,
        plan_id,
    )

    plan_key = plan.key

    subscription_plan_service.delete_plan(
        db,
        plan_id=plan_id,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_subscription_plan_deleted",
        entity_type="subscription_plan",
        entity_id=str(plan_id),
        description=f"Deleted subscription plan {plan_key}.",
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get("user-agent"),
    )

    return SuccessResponse(
        message="Subscription plan deleted successfully.",
    )


@router.post(
    "/subscription-plans/seed-defaults",
    response_model=SubscriptionPlanSeedResponse,
)
def seed_default_subscription_plans(
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = subscription_plan_service.seed_defaults(db)

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_subscription_plans_seeded",
        entity_type="subscription_plans",
        entity_id=None,
        description="Seeded default subscription plans.",
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get("user-agent"),
    )

    return result