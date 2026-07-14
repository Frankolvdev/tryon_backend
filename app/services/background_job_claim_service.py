import json
from datetime import timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
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
from app.schemas.background_job_runtime import (
    BackgroundJobClaimedItem,
    BackgroundJobClaimRequest,
    BackgroundJobClaimResponse,
    BackgroundJobHeartbeatRequest,
    BackgroundJobHeartbeatResponse,
    BackgroundJobRecoveryResponse,
)
from app.services.background_job_dependency_service import (
    background_job_dependency_service,
)
from app.services.background_job_redis_service import (
    background_job_redis_service,
)
from app.services.background_job_service import (
    background_job_service,
)


class BackgroundJobClaimService:
    CLAIMABLE_STATUSES = {
        JobStatus.PENDING.value,
        JobStatus.SCHEDULED.value,
        JobStatus.QUEUED.value,
        JobStatus.RETRYING.value,
    }

    LEASED_STATUSES = {
        JobStatus.CLAIMED.value,
        JobStatus.RUNNING.value,
        JobStatus.CANCEL_REQUESTED.value,
    }

    def _serialize_json(
        self,
        value: Any,
    ) -> str:
        return json.dumps(
            value or {},
            ensure_ascii=False,
            default=str,
        )

    def _parse_json(
        self,
        value: str | None,
    ) -> dict[str, Any]:
        if not value:
            return {}

        try:
            parsed = json.loads(value)

            return (
                parsed
                if isinstance(parsed, dict)
                else {}
            )

        except (
            json.JSONDecodeError,
            TypeError,
        ):
            return {}

    def _mark_dependency_failure(
        self,
        *,
        job: BackgroundJob,
        reason: str,
    ) -> None:
        now = utc_now()

        job.status = JobStatus.DEAD_LETTER.value
        job.error_code = "dependency_failed"
        job.error_message = reason
        job.error_details_json = self._serialize_json(
            {
                "reason": reason,
            }
        )
        job.completed_at = now
        job.progress_message = (
            "Job cannot execute because a required "
            "dependency failed."
        )

    def claim(
        self,
        db: Session,
        *,
        data: BackgroundJobClaimRequest,
    ) -> BackgroundJobClaimResponse:
        now = utc_now()

        # Fetch more candidates than requested because some may still
        # be waiting for dependencies.
        candidate_limit = min(
            max(data.max_jobs * 5, data.max_jobs),
            100,
        )

        candidates = (
            background_job_repository.list_claimable(
                db,
                queue_name=data.queue_name,
                now=now,
                limit=candidate_limit,
            )
        )

        claimed_items: list[
            BackgroundJobClaimedItem
        ] = []

        for job in candidates:
            if len(claimed_items) >= data.max_jobs:
                break

            ready, impossible, reason = (
                background_job_dependency_service
                .evaluate(
                    db,
                    job=job,
                )
            )

            if impossible:
                self._mark_dependency_failure(
                    job=job,
                    reason=(
                        reason
                        or "A required dependency failed."
                    ),
                )

                db.add(job)
                continue

            if not ready:
                continue

            lease_token = uuid4().hex
            lease_expires_at = now + timedelta(
                seconds=data.lease_seconds
            )

            job.status = JobStatus.CLAIMED.value
            job.claimed_at = now
            job.last_heartbeat_at = now
            job.lease_owner = data.worker_name
            job.lease_token = lease_token
            job.lease_expires_at = (
                lease_expires_at
            )
            job.worker_name = data.worker_name
            job.worker_version = (
                data.worker_version
            )
            job.attempt_count += 1
            job.progress_message = (
                "Job claimed by worker."
            )

            attempt = BackgroundJobAttempt(
                background_job_id=job.id,
                attempt_number=job.attempt_count,
                status=JobAttemptStatus.STARTED.value,
                worker_name=data.worker_name,
                lease_token=lease_token,
                started_at=now,
            )

            db.add(job)
            db.add(attempt)
            db.flush()

            claimed_items.append(
                BackgroundJobClaimedItem(
                    job=background_job_service
                    ._job_response(job),
                    lease_token=lease_token,
                    attempt_id=attempt.id,
                    attempt_number=(
                        attempt.attempt_number
                    ),
                )
            )

        db.commit()

        # Refresh after commit so timestamps and ORM state are current.
        for claimed_item in claimed_items:
            job = background_job_repository.get_by_id(
                db,
                claimed_item.job.id,
            )

            if job:
                claimed_item.job = (
                    background_job_service
                    ._job_response(job)
                )

                background_job_redis_service.publish_status(
                    public_id=job.public_id,
                    status=job.status,
                    progress=job.progress,
                    message=job.progress_message,
                    metadata={
                        "worker_name": (
                            data.worker_name
                        ),
                    },
                )

        return BackgroundJobClaimResponse(
            items=claimed_items,
            claimed=len(claimed_items),
            queue_name=data.queue_name,
            worker_name=data.worker_name,
        )

    def _get_leased_job_for_update(
        self,
        db: Session,
        *,
        job_id: int,
        worker_name: str,
        lease_token: str,
    ) -> BackgroundJob:
        job = (
            background_job_repository.get_for_update(
                db,
                job_id,
            )
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
                "Invalid or expired lease token."
            )

        if (
            job.lease_expires_at is None
            or job.lease_expires_at <= utc_now()
        ):
            db.rollback()

            raise ConflictException(
                "Background job lease has expired."
            )

        return job

    def start(
        self,
        db: Session,
        *,
        job_id: int,
        worker_name: str,
        lease_token: str,
    ):
        job = self._get_leased_job_for_update(
            db,
            job_id=job_id,
            worker_name=worker_name,
            lease_token=lease_token,
        )

        if job.status == JobStatus.RUNNING.value:
            db.commit()

            return background_job_service._job_response(
                job
            )

        if job.status != JobStatus.CLAIMED.value:
            db.rollback()

            raise ConflictException(
                "Only a claimed job can be started."
            )

        now = utc_now()

        job.status = JobStatus.RUNNING.value
        job.started_at = job.started_at or now
        job.last_heartbeat_at = now
        job.progress_message = (
            "Job execution started."
        )

        db.add(job)
        db.commit()
        db.refresh(job)

        background_job_redis_service.publish_status(
            public_id=job.public_id,
            status=job.status,
            progress=job.progress,
            message=job.progress_message,
            metadata={
                "worker_name": worker_name,
            },
        )

        return background_job_service._job_response(
            job
        )

    def heartbeat(
        self,
        db: Session,
        *,
        job_id: int,
        data: BackgroundJobHeartbeatRequest,
    ) -> BackgroundJobHeartbeatResponse:
        job = self._get_leased_job_for_update(
            db,
            job_id=job_id,
            worker_name=data.worker_name,
            lease_token=data.lease_token,
        )

        if job.status not in self.LEASED_STATUSES:
            db.rollback()

            raise ConflictException(
                "Job does not currently have an active lease."
            )

        now = utc_now()

        job.last_heartbeat_at = now
        job.lease_expires_at = now + timedelta(
            seconds=data.lease_seconds
        )

        if data.progress is not None:
            job.progress = data.progress

        if data.progress_message is not None:
            job.progress_message = (
                data.progress_message
            )

        metadata = self._parse_json(
            job.metadata_json
        )

        metadata.update(data.metadata)

        job.metadata_json = self._serialize_json(
            metadata
        )

        db.add(job)
        db.commit()
        db.refresh(job)

        background_job_redis_service.publish_status(
            public_id=job.public_id,
            status=job.status,
            progress=job.progress,
            message=job.progress_message,
            metadata={
                "worker_name": data.worker_name,
                **data.metadata,
            },
        )

        return BackgroundJobHeartbeatResponse(
            job_id=job.id,
            public_id=job.public_id,
            status=job.status,
            lease_expires_at=job.lease_expires_at,
            cancel_requested=(
                job.status
                == JobStatus.CANCEL_REQUESTED.value
            ),
            progress=job.progress,
            progress_message=job.progress_message,
        )

    def recover_expired_leases(
        self,
        db: Session,
        *,
        limit: int = 100,
    ) -> BackgroundJobRecoveryResponse:
        now = utc_now()

        statement = (
            select(BackgroundJob)
            .where(
                BackgroundJob.status.in_(
                    list(self.LEASED_STATUSES)
                ),
                BackgroundJob.lease_expires_at.is_not(
                    None
                ),
                BackgroundJob.lease_expires_at <= now,
            )
            .order_by(
                BackgroundJob.lease_expires_at.asc()
            )
            .with_for_update(skip_locked=True)
            .limit(limit)
        )

        jobs = list(
            db.execute(statement).scalars().all()
        )

        recovered = 0
        dead_lettered = 0
        failed = 0
        errors: list[dict[str, Any]] = []

        for job in jobs:
            try:
                latest_attempt = (
                    background_job_attempt_repository
                    .get_latest_for_job(
                        db,
                        background_job_id=job.id,
                    )
                )

                if latest_attempt:
                    latest_attempt.status = (
                        JobAttemptStatus.LOST.value
                    )
                    latest_attempt.completed_at = now
                    latest_attempt.error_code = (
                        "worker_lease_expired"
                    )
                    latest_attempt.error_message = (
                        "Worker heartbeat stopped and "
                        "the job lease expired."
                    )

                    if latest_attempt.started_at:
                        latest_attempt.duration_seconds = (
                            now
                            - latest_attempt.started_at
                        ).total_seconds()

                    db.add(latest_attempt)

                job.lease_owner = None
                job.lease_token = None
                job.lease_expires_at = None
                job.last_heartbeat_at = None
                job.worker_name = None
                job.worker_version = None

                if (
                    job.status
                    == JobStatus.CANCEL_REQUESTED.value
                ):
                    job.status = JobStatus.CANCELED.value
                    job.canceled_at = now
                    job.completed_at = now
                    job.progress_message = (
                        "Job canceled after worker lease expired."
                    )

                    dead_lettered += 1

                elif job.attempt_count >= job.max_attempts:
                    job.status = (
                        JobStatus.DEAD_LETTER.value
                    )
                    job.completed_at = now
                    job.error_code = (
                        "max_attempts_exhausted"
                    )
                    job.error_message = (
                        "Worker lease expired and the job "
                        "exhausted all attempts."
                    )
                    job.progress_message = (
                        "Job moved to dead-letter state."
                    )

                    dead_lettered += 1

                else:
                    backoff = int(
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
                        seconds=backoff
                    )
                    job.queued_at = None
                    job.claimed_at = None
                    job.started_at = None
                    job.progress_message = (
                        "Worker lease expired. "
                        "Job scheduled for retry."
                    )

                    recovered += 1

                db.add(job)

            except Exception as error:
                failed += 1

                errors.append(
                    {
                        "job_id": job.id,
                        "public_id": job.public_id,
                        "error": str(error),
                    }
                )

        db.commit()

        for job in jobs:
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
            )

        return BackgroundJobRecoveryResponse(
            inspected=len(jobs),
            recovered=recovered,
            dead_lettered=dead_lettered,
            failed=failed,
            errors=errors,
        )


background_job_claim_service = (
    BackgroundJobClaimService()
)