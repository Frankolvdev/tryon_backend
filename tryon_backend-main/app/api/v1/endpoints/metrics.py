from fastapi import (
    APIRouter,
    Depends,
    Response,
)
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    generate_latest,
)
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.services.operational_metrics_service import (
    operational_metrics_service,
)


router = APIRouter()


@router.get(
    "",
    include_in_schema=False,
)
def prometheus_metrics(
    db: Session = Depends(get_db),
):
    operational_metrics_service.collect_all(
        db
    )

    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )