from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import (
    admin_guard,
)
from app.models.user import User
from app.schemas.anti_abuse_operations import (
    AntiAbuseCleanupRequest,
    AntiAbuseCleanupResponse,
    AntiAbuseJobCatalogResponse,
    AntiAbuseJobResult,
    AntiAbuseJobRunRequest,
    AntiAbuseMetricsResponse,
    AntiAbuseValidationResponse,
)
from app.services.anti_abuse_cleanup_service import (
    anti_abuse_cleanup_service,
)
from app.services.anti_abuse_job_service import (
    anti_abuse_job_service,
)
from app.services.anti_abuse_metrics_service import (
    anti_abuse_metrics_service,
)
from app.services.anti_abuse_validation_service import (
    anti_abuse_validation_service,
)
from app.services.audit_service import (
    audit_service,
)

router = APIRouter()


@router.get(
    "/anti-abuse/metrics",
    response_model=AntiAbuseMetricsResponse,
)
def get_anti_abuse_metrics(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return anti_abuse_metrics_service.get_metrics(
        db,
        start=start,
        end=end,
    )


@router.get(
    "/anti-abuse/validation",
    response_model=AntiAbuseValidationResponse,
)
def validate_anti_abuse_configuration(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return anti_abuse_validation_service.validate(
        db
    )


@router.post(
    "/anti-abuse/cleanup",
    response_model=AntiAbuseCleanupResponse,
)
def run_anti_abuse_cleanup(
    data: AntiAbuseCleanupRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = anti_abuse_cleanup_service.run(
        db,
        options=data,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_anti_abuse_cleanup_executed",
        entity_type="anti_abuse_cleanup",
        entity_id=None,
        description=(
            "Executed anti-abuse cleanup. "
            f"Processed: {result.total_processed}; "
            f"failed: {result.total_failed}."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return result


@router.get(
    "/anti-abuse/jobs",
    response_model=AntiAbuseJobCatalogResponse,
)
def list_anti_abuse_jobs(
    current_admin: User = Depends(admin_guard),
):
    return anti_abuse_job_service.catalog()


@router.post(
    "/anti-abuse/jobs/{job_name}/run",
    response_model=AntiAbuseJobResult,
)
def run_anti_abuse_job(
    job_name: str,
    data: AntiAbuseJobRunRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = anti_abuse_job_service.run(
        db,
        job_name=job_name,
        max_items=data.max_items,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_anti_abuse_job_executed",
        entity_type="anti_abuse_job",
        entity_id=job_name,
        description=(
            f"Executed anti-abuse job {job_name}. "
            f"Processed: {result.processed}; "
            f"failed: {result.failed}."
        ),
        ip_address=(
            request.client.host
            if request.client
            else None
        ),
        user_agent=request.headers.get(
            "user-agent"
        ),
    )

    return result