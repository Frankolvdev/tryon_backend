from fastapi import (
    APIRouter,
    Depends,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.schemas.health import (
    LivenessResponse,
    ReadinessResponse,
)
from app.services.application_health_service import (
    application_health_service,
)


router = APIRouter()


@router.get(
    "/live",
    response_model=LivenessResponse,
)
def liveness():
    return (
        application_health_service
        .liveness()
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
)
def readiness(
    response: Response,
    db: Session = Depends(get_db),
):
    result = (
        application_health_service
        .readiness(db)
    )

    if not result.ready:
        response.status_code = (
            status.HTTP_503_SERVICE_UNAVAILABLE
        )

    return result