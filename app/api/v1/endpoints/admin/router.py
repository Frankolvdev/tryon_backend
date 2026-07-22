from fastapi import APIRouter

from app.api.v1.endpoints.admin import (
    abuse_events,
    account_security,
    activity,
    analytics,
    anti_abuse_operations,
    ai_providers,
    api_keys,
    audit,
    audit_entries,
    audit_operations,
    audit_restorations,
    background_job_operations,
    background_jobs,
    billing_analytics,
    billing_coupons,
    billing_events,
    billing_invoices,
    billing_operations,
    billing_payments,
    cache,
    cache_locks,
    cache_operations,
    comfyui,
    configuration,
    dashboard,
    default_rbac,
    default_scheduler_jobs,
    default_settings,
    external_ai_jobs,
    feature_flags,
    generation_modules,
    i18n,
    integrations,
    integrations_extra,
    monitoring,
    notification_center,
    notification_preferences,
    notifications,
    observability_health,
    observability_operations,
    operational_events,
    pricing,
    rate_limits,
    rbac,
    reports,
    runpod,
    scheduler,
    simulated_engine,
    search,
    security_blocks,
    storage,
    user_library,
    subscription_plans,
    subscriptions,
    support,
    system,
    system_status,
    token_purchases,
    tokens,
    tryon,
    user_announcements,
    users,
    webhooks,
    workflow_definitions,
)

admin_router = APIRouter()

admin_router.include_router(
    ai_providers.router,
    tags=["Admin - AI Providers"],
)

admin_router.include_router(
    account_security.router,
    tags=["Admin - Account Security"],
)
admin_router.include_router(
    dashboard.router,
    tags=["Admin - Dashboard"],
)
admin_router.include_router(
    analytics.router,
    tags=["Admin - Analytics"],
)
admin_router.include_router(
    monitoring.router,
    tags=["Admin - Monitoring"],
)
admin_router.include_router(
    observability_health.router,
    tags=["Admin - Observability"],
)
admin_router.include_router(
    observability_operations.router,
    tags=["Admin - Observability"],
)
admin_router.include_router(
    operational_events.router,
    tags=["Admin - Operational Events"],
)
admin_router.include_router(
    audit_entries.router,
    tags=["Admin - Advanced Audit"],
)
admin_router.include_router(
    audit_restorations.router,
    tags=["Admin - Audit Restorations"],
)
admin_router.include_router(
    audit_operations.router,
    tags=["Admin - Audit Operations"],
)
admin_router.include_router(
    notification_center.router,
    tags=["Admin - Notification Center"],
)
admin_router.include_router(
    notification_preferences.router,
    tags=["Admin - Notification Preferences"],
)
admin_router.include_router(
    user_announcements.router,
    tags=["Admin - User Announcements"],
)
admin_router.include_router(
    users.router,
    tags=["Admin - Users"],
)
admin_router.include_router(
    tokens.router,
    tags=["Admin - Tokens"],
)
admin_router.include_router(
    token_purchases.router,
    tags=["Admin - Token Purchases"],
)
admin_router.include_router(
    billing_payments.router,
    tags=["Admin - Billing Payments"],
)
admin_router.include_router(
    billing_coupons.router,
    tags=["Admin - Billing Coupons"],
)
admin_router.include_router(
    billing_events.router,
    tags=["Admin - Billing Events"],
)
admin_router.include_router(
    billing_invoices.router,
    tags=["Admin - Billing Invoices"],
)
admin_router.include_router(
    billing_analytics.router,
    tags=["Admin - Billing Analytics"],
)
admin_router.include_router(
    billing_operations.router,
    tags=["Admin - Billing Operations"],
)
admin_router.include_router(
    background_jobs.router,
    tags=["Admin - Background Jobs"],
)
admin_router.include_router(
    background_job_operations.router,
    tags=["Admin - Background Job Operations"],
)
admin_router.include_router(
    workflow_definitions.router,
    tags=["Admin - Workflow Definitions"],
)
admin_router.include_router(
    generation_modules.router,
    tags=["Admin - Generation Modules"],
)
admin_router.include_router(
    cache.router,
    tags=["Admin - Cache"],
)
admin_router.include_router(
    cache_locks.router,
    tags=["Admin - Cache Locks"],
)
admin_router.include_router(
    cache_operations.router,
    tags=["Admin - Cache Operations"],
)
admin_router.include_router(
    rate_limits.router,
    tags=["Admin - Rate Limits"],
)
admin_router.include_router(
    abuse_events.router,
    tags=["Admin - Abuse Events"],
)
admin_router.include_router(
    security_blocks.router,
    tags=["Admin - Security Blocks"],
)
admin_router.include_router(
    anti_abuse_operations.router,
    tags=["Admin - Anti-Abuse Operations"],
)
admin_router.include_router(
    tryon.router,
    tags=["Admin - Try-On"],
)
admin_router.include_router(
    pricing.router,
    tags=["Admin - Pricing"],
)
admin_router.include_router(
    subscription_plans.router,
    tags=["Admin - Subscription Plans"],
)
admin_router.include_router(
    subscriptions.router,
    tags=["Admin - Subscriptions"],
)
admin_router.include_router(
    simulated_engine.router,
    tags=["Admin - Simulated Engine"],
)
admin_router.include_router(
    runpod.router,
    tags=["Admin - RunPod"],
)
admin_router.include_router(
    storage.router,
    tags=["Admin - Storage"],
)
admin_router.include_router(
    system.router,
    tags=["Admin - System"],
)
admin_router.include_router(
    default_settings.router,
    tags=["Admin - System"],
)
admin_router.include_router(
    configuration.router,
    tags=["Admin - System"],
)
admin_router.include_router(
    system_status.router,
    tags=["Admin - System Status"],
)
admin_router.include_router(
    feature_flags.router,
    tags=["Admin - Feature Flags"],
)
admin_router.include_router(
    i18n.router,
    tags=["Admin - Internationalization"],
)
admin_router.include_router(
    reports.router,
    tags=["Admin - Reports"],
)
admin_router.include_router(
    notifications.router,
    tags=["Admin - Notifications"],
)
admin_router.include_router(
    support.router,
    tags=["Admin - Support"],
)
admin_router.include_router(
    search.router,
    tags=["Admin - Search"],
)
admin_router.include_router(
    scheduler.router,
    tags=["Admin - Scheduler"],
)
admin_router.include_router(
    default_scheduler_jobs.router,
    tags=["Admin - Scheduler"],
)
admin_router.include_router(
    rbac.router,
    tags=["Admin - RBAC"],
)
admin_router.include_router(
    default_rbac.router,
    tags=["Admin - RBAC"],
)
admin_router.include_router(
    api_keys.router,
    tags=["Admin - API Keys"],
)
admin_router.include_router(
    webhooks.router,
    tags=["Admin - Webhooks"],
)
admin_router.include_router(
    integrations.router,
    tags=["Admin - Integrations"],
)
admin_router.include_router(
    integrations_extra.router,
    tags=["Admin - Integrations"],
)
admin_router.include_router(
    external_ai_jobs.router,
    tags=["Admin - External AI Jobs"],
)
admin_router.include_router(
    comfyui.router,
    tags=["Admin - ComfyUI"],
)
admin_router.include_router(
    audit.router,
    tags=["Admin - Audit"],
)
admin_router.include_router(
    activity.router,
    tags=["Admin - Activity"],
)

admin_router.include_router(user_library.router, tags=["User Library Admin"])
