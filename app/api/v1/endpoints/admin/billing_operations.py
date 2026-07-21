from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import admin_guard
from app.models.user import User
from app.schemas.billing_operations import (
    BillingJobResult,
    BillingJobRunRequest,
    BillingJobsCatalogResponse,
    BillingOperationsOverview,
    BillingValidationResponse,
)
from app.services.audit_service import audit_service
from app.services.billing_job_service import (
    billing_job_service,
)
from app.services.billing_operations_overview_service import (
    billing_operations_overview_service,
)
from app.services.billing_validation_service import (
    billing_validation_service,
)

router = APIRouter()


@router.get(
    "/billing/overview",
    response_model=BillingOperationsOverview,
)
def get_billing_operations_overview(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return billing_operations_overview_service.get(db)


@router.get(
    "/billing/validation",
    response_model=BillingValidationResponse,
)
def validate_billing_configuration(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return billing_validation_service.validate(db)


@router.get(
    "/billing/jobs",
    response_model=BillingJobsCatalogResponse,
)
def list_billing_jobs(
    current_admin: User = Depends(admin_guard),
):
    return billing_job_service.catalog()


@router.post(
    "/billing/jobs/{job_name}/run",
    response_model=BillingJobResult,
)
def run_billing_job(
    job_name: str,
    data: BillingJobRunRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = billing_job_service.run(
        db,
        job_name=job_name,
        max_items=data.max_items,
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action="admin_billing_job_executed",
        entity_type="billing_job",
        entity_id=job_name,
        description=(
            f"Executed Billing job {job_name}. "
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