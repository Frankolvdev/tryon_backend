from sqlalchemy.orm import Session

from app.schemas.background_job import (
    BackgroundJobCancelResponse,
    BackgroundJobCreate,
    BackgroundJobRetryRequest,
    BackgroundJobRetryResponse,
    UserBackgroundJobCreate,
)
from app.services.background_job_redis_service import (
    background_job_redis_service,
)
from app.services.background_job_service import (
    background_job_service,
)


class BackgroundJobDispatchService:
    def create_job(
        self,
        db: Session,
        *,
        data: BackgroundJobCreate,
    ):
        result, created = (
            background_job_service.create_job(
                db,
                data=data,
            )
        )

        if created:
            background_job_redis_service.notify_queue(
                queue_name=result.queue_name.value,
                job_public_id=result.public_id,
            )

        return result, created

    def create_user_job(
        self,
        db: Session,
        *,
        user_id: int,
        data: UserBackgroundJobCreate,
    ):
        result, created = (
            background_job_service.create_user_job(
                db,
                user_id=user_id,
                data=data,
            )
        )

        if created:
            background_job_redis_service.notify_queue(
                queue_name=result.queue_name.value,
                job_public_id=result.public_id,
            )

        return result, created

    def retry_job(
        self,
        db: Session,
        *,
        job_id: int,
        data: BackgroundJobRetryRequest,
    ) -> BackgroundJobRetryResponse:
        result = background_job_service.retry_job(
            db,
            job_id=job_id,
            data=data,
        )

        background_job_redis_service.notify_queue(
            queue_name=result.job.queue_name.value,
            job_public_id=result.job.public_id,
        )

        background_job_redis_service.publish_status(
            public_id=result.job.public_id,
            status=result.job.status.value,
            progress=result.job.progress,
            message=result.job.progress_message,
        )

        return result

    def cancel_job(
        self,
        db: Session,
        *,
        job_id: int,
        reason: str | None = None,
        user_id: int | None = None,
    ) -> BackgroundJobCancelResponse:
        result = (
            background_job_service
            .request_cancellation(
                db,
                job_id=job_id,
                reason=reason,
                user_id=user_id,
            )
        )

        background_job_redis_service.publish_status(
            public_id=result.job.public_id,
            status=result.job.status.value,
            progress=result.job.progress,
            message=result.job.progress_message,
            metadata={
                "cancellation_requested": (
                    result.cancellation_requested
                ),
                "canceled_immediately": (
                    result.canceled_immediately
                ),
            },
        )

        return result


background_job_dispatch_service = (
    BackgroundJobDispatchService()
)