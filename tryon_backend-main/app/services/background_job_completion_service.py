import json
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.common.exceptions import (
    ConflictException,
    NotFoundException,
)
from app.common.job_enums import (
    JobAttemptStatus,
    JobStatus,
)
from app.common.time import utc_now
from app.models.background_job import BackgroundJob
from app.models.background_job_attempt import (
    BackgroundJobAttempt,
)
from app.repositories.background_job_attempt_repository import (
    background_job_attempt_repository,
)
from app.repositories.background_job_repository import (
    background_job_repository,
)
from app.services.background_job_redis_service import (
    background_job_redis_service,
)
from app.services.background_job_service import (
    background_job_service,
)


class BackgroundJobCompletionService:
    def _serialize_json(
        self,
        value: Any,
    ) -> str:
        return json.dumps(
            value or {},
            ensure_ascii=False,
            default=str,
        )

    def _get_leased_job(
        self,
        db: Session,
        *,
        job_id: int,
        worker_name: str,
        lease_token: str,
    ) -> BackgroundJob:
        job = background_job_repository.get_for_update(
            db,
            job_id,
        )

        if not job:
            raise NotFoundException(
                "Background job not found."
            )

        if job.lease_owner != worker_name:
            db.rollback()

            raise ConflictException(
                "Job lease belongs to another worker."
            )

        if job.lease_token != lease_token:
            db.rollback()

            raise ConflictException(
                "Invalid background job lease token."
            )

        return job

    def _get_active_attempt(
        self,
        db: Session,
        *,
        job_id: int,
    ) -> BackgroundJobAttempt | None:
        return (
            background_job_attempt_repository
            .get_latest_for_job(
                db,
                background_job_id=job_id,
            )
        )

    def _duration_seconds(
        self,
        attempt: BackgroundJobAttempt,
    ) -> float:
        now = utc_now()

        return max(
            (
                now - attempt.started_at
            ).total_seconds(),
            0.0,
        )

    def _clear_lease(
        self,
        job: BackgroundJob,
    ) -> None:
        job.lease_owner = None
        job.lease_token = None
        job.lease_expires_at = None
        job.last_heartbeat_at = None
        job.worker_name = None
        job.worker_version = None

    def succeed(
        self,
        db: Session,
        *,
        job_id: int,
        worker_name: str,
        lease_token: str,
        result: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
    ):
        job = self._get_leased_job(
            db,
            job_id=job_id,
            worker_name=worker_name,
            lease_token=lease_token,
        )

        if (
            job.status
            == JobStatus.CANCEL_REQUESTED.value
        ):
            db.rollback()

            return self.cancel(
                db,
                job_id=job_id,
                worker_name=worker_name,
                lease_token=lease_token,
                reason=(
                    "Cancellation was requested before "
                    "the job completed."
                ),
            )

        if job.status not in {
            JobStatus.CLAIMED.value,
            JobStatus.RUNNING.value,
        }:
            db.rollback()

            raise ConflictException(
                "Job cannot be completed from its "
                "current state."
            )

        now = utc_now()

        attempt = self._get_active_attempt(
            db,
            job_id=job.id,
        )

        if attempt:
            attempt.status = (
                JobAttemptStatus.SUCCEEDED.value
            )
            attempt.completed_at = now
            attempt.duration_seconds = (
                self._duration_seconds(attempt)
            )
            attempt.result_json = (
                self._serialize_json(result)
            )
            attempt.metrics_json = (
                self._serialize_json(metrics)
            )

            db.add(attempt)

        job.status = JobStatus.SUCCEEDED.value
        job.result_json = self._serialize_json(
            result
        )
        job.error_code = None
        job.error_message = None
        job.error_details_json = None
        job.progress = 100.0
        job.progress_message = (
            "Job completed successfully."
        )
        job.completed_at = now

        self._clear_lease(job)

        db.add(job)
        db.commit()
        db.refresh(job)

        background_job_redis_service.publish_status(
            public_id=job.public_id,
            status=job.status,
            progress=job.progress,
            message=job.progress_message,
            metadata={
                "result": result or {},
                "metrics": metrics or {},
            },
        )

        return background_job_service._job_response(
            job
        )

    def fail(
        self,
        db: Session,
        *,
        job_id: int,
        worker_name: str,
        lease_token: str,
        error_code: str,
        error_message: str,
        error_details: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        timed_out: bool = False,
        retryable: bool = True,
    ):
        job = self._get_leased_job(
            db,
            job_id=job_id,
            worker_name=worker_name,
            lease_token=lease_token,
        )

        now = utc_now()

        attempt = self._get_active_attempt(
            db,
            job_id=job.id,
        )

        if attempt:
            attempt.status = (
                JobAttemptStatus.TIMED_OUT.value
                if timed_out
                else JobAttemptStatus.FAILED.value
            )
            attempt.completed_at = now
            attempt.duration_seconds = (
                self._duration_seconds(attempt)
            )
            attempt.error_code = error_code
            attempt.error_message = error_message
            attempt.error_details_json = (
                self._serialize_json(
                    error_details
                )
            )
            attempt.metrics_json = (
                self._serialize_json(metrics)
            )

            db.add(attempt)

        exhausted = (
            job.attempt_count >= job.max_attempts
        )

        should_retry = (
            retryable
            and not exhausted
            and job.status
            != JobStatus.CANCEL_REQUESTED.value
        )

        job.error_code = error_code
        job.error_message = error_message
        job.error_details_json = (
            self._serialize_json(
                error_details
            )
        )

        if should_retry:
            backoff_seconds = int(
                job.retry_backoff_seconds
                * (
                    job.retry_backoff_multiplier
                    ** max(
                        job.attempt_count - 1,
                        0,
                    )
                )
            )

            job.status = JobStatus.RETRYING.value
            job.available_at = now + timedelta(
                seconds=backoff_seconds
            )
            job.completed_at = None
            job.progress = 0.0
            job.progress_message = (
                "Job failed and was scheduled "
                "for automatic retry."
            )
            job.claimed_at = None
            job.started_at = None

        elif (
            job.status
            == JobStatus.CANCEL_REQUESTED.value
        ):
            job.status = JobStatus.CANCELED.value
            job.canceled_at = now
            job.completed_at = now
            job.progress_message = (
                "Job canceled during execution."
            )

        elif exhausted:
            job.status = JobStatus.DEAD_LETTER.value
            job.completed_at = now
            job.progress_message = (
                "Job exhausted all attempts and "
                "was moved to dead-letter state."
            )

        elif timed_out:
            job.status = JobStatus.TIMED_OUT.value
            job.completed_at = now
            job.progress_message = (
                "Job execution timed out."
            )

        else:
            job.status = JobStatus.FAILED.value
            job.completed_at = now
            job.progress_message = (
                "Job execution failed."
            )

        self._clear_lease(job)

        db.add(job)
        db.commit()
        db.refresh(job)

        if job.status == JobStatus.RETRYING.value:
            background_job_redis_service.notify_queue(
                queue_name=job.queue_name,
                job_public_id=job.public_id,
            )

        background_job_redis_service.publish_status(
            public_id=job.public_id,
            status=job.status,
            progress=job.progress,
            message=job.progress_message,
            metadata={
                "error_code": error_code,
                "error_message": error_message,
                "retry_scheduled": (
                    job.status
                    == JobStatus.RETRYING.value
                ),
            },
        )

        return background_job_service._job_response(
            job
        )

    def cancel(
        self,
        db: Session,
        *,
        job_id: int,
        worker_name: str,
        lease_token: str,
        reason: str | None = None,
    ):
        job = self._get_leased_job(
            db,
            job_id=job_id,
            worker_name=worker_name,
            lease_token=lease_token,
        )

        now = utc_now()

        attempt = self._get_active_attempt(
            db,
            job_id=job.id,
        )

        if attempt:
            attempt.status = (
                JobAttemptStatus.CANCELED.value
            )
            attempt.completed_at = now
            attempt.duration_seconds = (
                self._duration_seconds(attempt)
            )
            attempt.error_code = "job_canceled"
            attempt.error_message = (
                reason or "Job canceled."
            )

            db.add(attempt)

        job.status = JobStatus.CANCELED.value
        job.canceled_at = now
        job.completed_at = now
        job.progress_message = (
            reason or "Job canceled."
        )

        self._clear_lease(job)

        db.add(job)
        db.commit()
        db.refresh(job)

        background_job_redis_service.publish_status(
            public_id=job.public_id,
            status=job.status,
            progress=job.progress,
            message=job.progress_message,
        )

        return background_job_service._job_response(
            job
        )


background_job_completion_service = (
    BackgroundJobCompletionService()
)