from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.common.billing_enums import SubscriptionStatus
from app.models.user import User
from app.schemas.subscription import (
    AdminSubscriptionListResponse,
    SubscriptionActionResponse,
    SubscriptionChangePlanRequest,
    SubscriptionSyncResponse,
)
from app.services.audit_service import audit_service
from app.services.subscription_service import subscription_service

router = APIRouter()


@router.get(
    "/subscriptions",
    response_model=AdminSubscriptionListResponse,
)
def list_subscriptions(
    user_id: int | None = Query(default=None),
    status: SubscriptionStatus | None = Query(default=None),
    plan_id: int | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return subscription_service.admin_list(
        db,
        user_id=user_id,
        status=status,
        plan_id=plan_id,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/subscriptions/users/{user_id}/cancel-at-period-end",
    response_model=SubscriptionActionResponse,
)
def admin_cancel_subscription_at_period_end(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = subscription_service.cancel_at_period_end(
        db,
        user_id=user_id,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_subscription_cancel_at_period_end",
        entity_type="user_subscription",
        entity_id=str(result.subscription.id),
        description=(
            f"Admin scheduled subscription cancellation "
            f"for user {user_id}."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get("user-agent"),
    )

    return result


@router.post(
    "/subscriptions/users/{user_id}/cancel-immediately",
    response_model=SubscriptionActionResponse,
)
def admin_cancel_subscription_immediately(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = subscription_service.cancel_immediately(
        db,
        user_id=user_id,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_subscription_canceled_immediately",
        entity_type="user_subscription",
        entity_id=str(result.subscription.id),
        description=(
            f"Admin canceled subscription immediately "
            f"for user {user_id}."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get("user-agent"),
    )

    return result


@router.post(
    "/subscriptions/users/{user_id}/reactivate",
    response_model=SubscriptionActionResponse,
)
def admin_reactivate_subscription(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = subscription_service.reactivate(
        db,
        user_id=user_id,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_subscription_reactivated",
        entity_type="user_subscription",
        entity_id=str(result.subscription.id),
        description=(
            f"Admin reactivated subscription "
            f"for user {user_id}."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get("user-agent"),
    )

    return result


@router.post(
    "/subscriptions/users/{user_id}/change-plan",
    response_model=SubscriptionActionResponse,
)
def admin_change_subscription_plan(
    user_id: int,
    data: SubscriptionChangePlanRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = subscription_service.change_plan(
        db,
        user_id=user_id,
        data=data,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_subscription_plan_changed",
        entity_type="user_subscription",
        entity_id=str(result.subscription.id),
        description=(
            f"Admin changed subscription plan "
            f"for user {user_id}."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get("user-agent"),
    )

    return result


@router.post(
    "/subscriptions/users/{user_id}/sync",
    response_model=SubscriptionSyncResponse,
)
def admin_sync_subscription(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = subscription_service.synchronize_subscription(
        db,
        user_id=user_id,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_subscription_synchronized",
        entity_type="user_subscription",
        entity_id=str(result.subscription.id),
        description=(
            f"Admin synchronized subscription "
            f"for user {user_id}."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get("user-agent"),
    )

    return result