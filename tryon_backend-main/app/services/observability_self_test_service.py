from uuid import uuid4

from prometheus_client import (
    generate_latest,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.common.time import utc_now
from app.core.redis_client import redis_client
from app.models.operational_event import (
    OperationalEvent,
)
from app.schemas.observability_maintenance import (
    ObservabilitySelfTestResponse,
)
from app.schemas.operational_event import (
    OperationalEventCreate,
)
from app.services.operational_event_service import (
    operational_event_service,
)


class ObservabilitySelfTestService:
    def run(
        self,
        db: Session,
    ) -> ObservabilitySelfTestResponse:
        test_id = uuid4().hex

        prometheus_registry_available = False
        postgres_available = False
        redis_available = False
        operational_event_created = False
        operational_event_deleted = False

        details: dict = {
            "test_id": test_id,
        }

        try:
            metrics_output = generate_latest()

            prometheus_registry_available = bool(
                metrics_output
            )

            details[
                "prometheus_bytes"
            ] = len(metrics_output)

        except Exception as error:
            details[
                "prometheus_error"
            ] = str(error)

        try:
            db.execute(
                text("SELECT 1")
            )

            postgres_available = True

        except Exception as error:
            details[
                "postgres_error"
            ] = str(error)

        try:
            redis_available = bool(
                redis_client.ping()
            )

        except Exception as error:
            details[
                "redis_error"
            ] = str(error)

        event_id: int | None = None

        try:
            created = (
                operational_event_service
                .create(
                    db,
                    data=OperationalEventCreate(
                        event_type=(
                            "observability_self_test"
                        ),
                        source="observability",
                        severity="info",
                        message=(
                            "Temporary observability "
                            "self-test event."
                        ),
                        details={
                            "test_id": test_id,
                            "temporary": True,
                        },
                    ),
                )
            )

            event_id = created.id
            operational_event_created = True

        except Exception as error:
            db.rollback()

            details[
                "event_create_error"
            ] = str(error)

        if event_id is not None:
            try:
                event = db.get(
                    OperationalEvent,
                    event_id,
                )

                if event:
                    db.delete(event)
                    db.commit()

                    operational_event_deleted = True

            except Exception as error:
                db.rollback()

                details[
                    "event_delete_error"
                ] = str(error)

        success = all(
            [
                prometheus_registry_available,
                postgres_available,
                redis_available,
                operational_event_created,
                operational_event_deleted,
            ]
        )

        return ObservabilitySelfTestResponse(
            success=success,
            prometheus_registry_available=(
                prometheus_registry_available
            ),
            postgres_available=(
                postgres_available
            ),
            redis_available=redis_available,
            operational_event_created=(
                operational_event_created
            ),
            operational_event_deleted=(
                operational_event_deleted
            ),
            details=details,
            checked_at=utc_now(),
        )


observability_self_test_service = (
    ObservabilitySelfTestService()
)