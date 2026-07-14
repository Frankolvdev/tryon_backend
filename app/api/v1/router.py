from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.endpoints import (
    account_verification,
    admin_mfa,
    auth,
    background_jobs,
    billing,
    billing_coupons,
    billing_history,
    email_change,
    feature_flags,
    health,
    i18n,
    job_progress,
    metrics,
    password_recovery,
    pricing,
    runpod_callbacks,
    sessions,
    stripe_webhooks,
    subscription_plans,
    support,
    system,
    tokens,
    tryon,
    user_notifications,
    users,
    webhooks,
    worker_jobs,
)
from app.api.v1.endpoints.admin.router import (
    admin_router,
)
from app.core.config import settings


api_router = APIRouter()


api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["Authentication"],
)

api_router.include_router(
    account_verification.router,
    prefix="/account-verification",
    tags=["Account Verification"],
)

api_router.include_router(
    password_recovery.router,
    prefix="/password-recovery",
    tags=["Password Recovery"],
)

api_router.include_router(
    email_change.router,
    prefix="/email-change",
    tags=["Email Change"],
)

api_router.include_router(
    admin_mfa.router,
    prefix="/admin-mfa",
    tags=["Administrative MFA"],
)

api_router.include_router(
    users.router,
    prefix="/users",
    tags=["Users"],
)

api_router.include_router(
    sessions.router,
    prefix="/sessions",
    tags=["Sessions"],
)

api_router.include_router(
    i18n.router,
    prefix="/i18n",
    tags=["Internationalization"],
)

api_router.include_router(
    tokens.router,
    prefix="/tokens",
    tags=["Tokens"],
)

api_router.include_router(
    pricing.router,
    prefix="/pricing",
    tags=["Pricing"],
)

api_router.include_router(
    subscription_plans.router,
    prefix="/subscription-plans",
    tags=["Subscription Plans"],
)

api_router.include_router(
    billing_coupons.router,
    prefix="/billing-coupons",
    tags=["Billing Coupons"],
)

api_router.include_router(
    billing.router,
    prefix="/billing",
    tags=["Billing"],
)

api_router.include_router(
    billing_history.router,
    prefix="/billing/history",
    tags=["Billing History"],
)

api_router.include_router(
    tryon.router,
    prefix="/tryon",
    tags=["Try-On"],
)

api_router.include_router(
    background_jobs.router,
    prefix="/background-jobs",
    tags=["Background Jobs"],
)

api_router.include_router(
    job_progress.router,
    prefix="/job-progress",
    tags=["Job Progress"],
)

api_router.include_router(
    worker_jobs.router,
    prefix="/worker-jobs",
    tags=["Worker Jobs"],
)

api_router.include_router(
    user_notifications.router,
    prefix="/user-notifications",
    tags=["User Notifications"],
)

api_router.include_router(
    feature_flags.router,
    prefix="/feature-flags",
    tags=["Feature Flags"],
)

api_router.include_router(
    system.router,
    prefix="/system",
    tags=["System"],
)

api_router.include_router(
    support.router,
    prefix="/support",
    tags=["Support"],
)

api_router.include_router(
    webhooks.router,
    prefix="/webhooks",
    tags=["Webhooks"],
)

api_router.include_router(
    stripe_webhooks.router,
    prefix="/webhooks",
    tags=["Stripe Webhooks"],
)

api_router.include_router(
    runpod_callbacks.router,
    prefix="/runpod",
    tags=["RunPod Callbacks"],
)

api_router.include_router(
    health.router,
    prefix="/health",
    tags=["Health"],
)

api_router.include_router(
    metrics.router,
    prefix="/metrics",
    tags=["Metrics"],
)

api_router.include_router(
    admin_router,
    prefix="/admin",
)


@api_router.get(
    "/health",
    tags=["Health"],
)
def health_check():
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@api_router.get(
    "/db-health",
    tags=["Health"],
)
def database_health_check(
    db: Session = Depends(get_db),
):
    db.execute(
        text("SELECT 1")
    )

    return {
        "status": "ok",
        "database": "connected",
    }