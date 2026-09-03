from fastapi import (
    APIRouter,
    Depends,
    Query,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.api.v1.guards.admin_guard import (
    admin_guard,
)
from app.models.user import User
from app.schemas.health import (
    SystemHealthResponse,
)
from app.services.application_health_service import (
    application_health_service,
)


router = APIRouter()


@router.get(
    "/observability/health",
    response_model=SystemHealthResponse,
)
def get_system_health(
    response: Response,
    perform_remote_checks: bool = Query(
        default=False,
    ),
    db: Session = Depends(get_db),
    current_admin: User = Depends(
        admin_guard
    ),
):
    result = (
        application_health_service
        .full_health(
            db,
            perform_remote_checks=(
                perform_remote_checks
            ),
        )
    )

    if not result.ready:
        response.status_code = (
            status.HTTP_503_SERVICE_UNAVAILABLE
        )

    return result