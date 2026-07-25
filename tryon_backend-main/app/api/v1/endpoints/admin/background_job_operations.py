from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
)
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import (
    admin_guard,
)
from app.models.user import User
from app.schemas.background_job_operations import (
    BackgroundJobMaintenanceRequest,
    BackgroundJobMaintenanceResponse,
    BackgroundJobMetricsResponse,
)
from app.services.audit_service import (
    audit_service,
)
from app.services.background_job_maintenance_service import (
    background_job_maintenance_service,
)
from app.services.background_job_metrics_service import (
    background_job_metrics_service,
)


router = APIRouter()


@router.get(
    "/background-job-operations/metrics",
    response_model=BackgroundJobMetricsResponse,
)
def get_background_job_metrics(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    return (
        background_job_metrics_service
        .get_metrics(
            db,
            start=start,
            end=end,
        )
    )


@router.post(
    "/background-job-operations/maintenance",
    response_model=(
        BackgroundJobMaintenanceResponse
    ),
)
def run_background_job_maintenance(
    data: BackgroundJobMaintenanceRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_guard),
):
    result = (
        background_job_maintenance_service
        .run(
            db,
            data=data,
        )
    )

    audit_service.create_log(
        db,
        actor_user_id=current_admin.id,
        action=(
            "admin_background_job_maintenance"
        ),
        entity_type="background_job",
        entity_id=None,
        description=(
            "Executed background-job maintenance. "
            f"Recovered: {result.recovered_jobs}; "
            f"dead-lettered: "
            f"{result.dead_lettered_jobs}."
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