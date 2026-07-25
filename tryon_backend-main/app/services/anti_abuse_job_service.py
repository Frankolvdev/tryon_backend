from sqlalchemy.orm import Session

from app.common.exceptions import (
    NotFoundException,
)
from app.jobs.security_jobs import (
    SECURITY_JOB_HANDLERS,
)
from app.schemas.anti_abuse_operations import (
    AntiAbuseJobCatalogItem,
    AntiAbuseJobCatalogResponse,
    AntiAbuseJobResult,
)


class AntiAbuseJobService:
    def catalog(
        self,
    ) -> AntiAbuseJobCatalogResponse:
        return AntiAbuseJobCatalogResponse(
            jobs=[
                AntiAbuseJobCatalogItem(
                    name=(
                        "security.cleanup_expired_blocks"
                    ),
                    description=(
                        "Deactivates temporary security blocks "
                        "whose expiration date has passed."
                    ),
                    recommended_schedule="*/10 * * * *",
                    enabled=True,
                ),
                AntiAbuseJobCatalogItem(
                    name="security.cleanup_old_events",
                    description=(
                        "Deletes resolved or ignored abuse events "
                        "older than 180 days."
                    ),
                    recommended_schedule="30 4 * * 0",
                    enabled=True,
                ),
                AntiAbuseJobCatalogItem(
                    name="security.daily_maintenance",
                    description=(
                        "Runs routine security cleanup operations."
                    ),
                    recommended_schedule="45 3 * * *",
                    enabled=True,
                ),
            ]
        )

    def run(
        self,
        db: Session,
        *,
        job_name: str,
        max_items: int,
    ) -> AntiAbuseJobResult:
        handler = SECURITY_JOB_HANDLERS.get(
            job_name
        )

        if not handler:
            raise NotFoundException(
                "Security job handler not found."
            )

        return handler(
            db,
            max_items=max_items,
        )


anti_abuse_job_service = AntiAbuseJobService()