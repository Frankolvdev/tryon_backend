import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.common.exceptions import (
    ConflictException,
    NotFoundException,
)
from app.common.job_enums import (
    JobAttemptStatus,
    JobDependencyType,
    JobPriority,
    JobStatus,
)
from app.common.time import utc_now
from app.models.background_job import BackgroundJob
from app.models.background_job_attempt import (
    BackgroundJobAttempt,
)
from app.models.background_job_dependency import (
    BackgroundJobDependency,
)
from app.repositories.background_job_attempt_repository import (
    background_job_attempt_repository,
)
from app.repositories.background_job_dependency_repository import (
    background_job_dependency_repository,
)
from app.repositories.background_job_repository import (
    background_job_repository,
)
from app.schemas.background_job import (
    BackgroundJobAttemptListResponse,
    BackgroundJobAttemptResponse,
    BackgroundJobCancelResponse,
    BackgroundJobCreate,
    BackgroundJobDependencyListResponse,
    BackgroundJobDependencyResponse,
    BackgroundJobDetailResponse,
    BackgroundJobListResponse,
    BackgroundJobProgressUpdate,
    BackgroundJobResponse,
    BackgroundJobRetryRequest,
    BackgroundJobRetryResponse,
    UserBackgroundJobCreate,
)


class BackgroundJobService:
    TERMINAL_STATUSES = {
        JobStatus.SUCCEEDED.value,
        JobStatus.FAILED.value,
        JobStatus.CANCELED.value,
        JobStatus.TIMED_OUT.value,
        JobStatus.DEAD_LETTER.value,
    }

    ACTIVE_STATUSES = {
        JobStatus.CLAIMED.value,
        JobStatus.RUNNING.value,
        JobStatus.CANCEL_REQUESTED.value,
    }

    RETRYABLE_STATUSES = {
        JobStatus.FAILED.value,
        JobStatus.TIMED_OUT.value,
        JobStatus.DEAD_LETTER.value,
        JobStatus.CANCELED.value,
    }

    IMMEDIATELY_CANCELABLE_STATUSES = {
        JobStatus.PENDING.value,
        JobStatus.SCHEDULED.value,
        JobStatus.QUEUED.value,
        JobStatus.RETRYING.value,
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

            if isinstance(parsed, dict):
                return parsed

            return {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _job_response(
        self,
        job: BackgroundJob,
    ) -> BackgroundJobResponse:
        parsed_result = (
            self._parse_json(job.result_json)
            if job.result_json
            else None
        )

        return BackgroundJobResponse(
            id=job.id,
            public_id=job.public_id,
            job_type=job.job_type,
            queue_name=job.queue_name,
            execution_mode=job.execution_mode,
            status=job.status,
            priority=job.priority,
            user_id=job.user_id,
            tryon_job_id=job.tryon_job_id,
            external_ai_job_id=job.external_ai_job_id,
            idempotency_key=job.idempotency_key,
            payload=self._parse_json(job.payload_json),
            result=parsed_result,
            metadata=self._parse_json(
                job.metadata_json
            ),
            error_code=job.error_code,
            error_message=job.error_message,
            error_details=self._parse_json(
                job.error_details_json
            ),
            progress=job.progress,
            progress_message=job.progress_message,
            attempt_count=job.attempt_count,
            max_attempts=job.max_attempts,
            retry_backoff_seconds=(
                job.retry_backoff_seconds
            ),
            retry_backoff_multiplier=(
                job.retry_backoff_multiplier
            ),
            timeout_seconds=job.timeout_seconds,
            scheduled_at=job.scheduled_at,
            available_at=job.available_at,
            queued_at=job.queued_at,
            claimed_at=job.claimed_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            canceled_at=job.canceled_at,
            cancel_requested_at=(
                job.cancel_requested_at
            ),
            last_heartbeat_at=job.last_heartbeat_at,
            lease_owner=job.lease_owner,
            lease_expires_at=job.lease_expires_at,
            provider_job_id=job.provider_job_id,
            provider_endpoint_id=(
                job.provider_endpoint_id
            ),
            worker_name=job.worker_name,
            worker_version=job.worker_version,
            is_cancelable=job.is_cancelable,
            retain_until=job.retain_until,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    def _attempt_response(
        self,
        attempt: BackgroundJobAttempt,
    ) -> BackgroundJobAttemptResponse:
        return BackgroundJobAttemptResponse(
            id=attempt.id,
            background_job_id=(
                attempt.background_job_id
            ),
            attempt_number=attempt.attempt_number,
            status=attempt.status,
            worker_name=attempt.worker_name,
            provider_job_id=attempt.provider_job_id,
            started_at=attempt.started_at,
            completed_at=attempt.completed_at,
            duration_seconds=attempt.duration_seconds,
            error_code=attempt.error_code,
            error_message=attempt.error_message,
            error_details=self._parse_json(
                attempt.error_details_json
            ),
            result=(
                self._parse_json(attempt.result_json)
                if attempt.result_json
                else None
            ),
            metrics=self._parse_json(
                attempt.metrics_json
            ),
            created_at=attempt.created_at,
            updated_at=attempt.updated_at,
        )

    def _dependency_response(
        self,
        dependency: BackgroundJobDependency,
    ) -> BackgroundJobDependencyResponse:
        return BackgroundJobDependencyResponse(
            id=dependency.id,
            background_job_id=(
                dependency.background_job_id
            ),
            depends_on_job_id=(
                dependency.depends_on_job_id
            ),
            dependency_type=(
                dependency.dependency_type
            ),
            created_at=dependency.created_at,
        )

    def get_job(
        self,
        db: Session,
        *,
        job_id: int,
        user_id: int | None = None,
    ) -> BackgroundJob:
        job = background_job_repository.get_by_id(
            db,
            job_id,
        )

        if not job:
            raise NotFoundException(
                "Background job not found."
            )

        if (
            user_id is not None
            and job.user_id != user_id
        ):
            raise NotFoundException(
                "Background job not found."
            )

        return job

    def get_job_by_public_id(
        self,
        db: Session,
        *,
        public_id: str,
        user_id: int | None = None,
    ) -> BackgroundJob:
        job = (
            background_job_repository
            .get_by_public_id(
                db,
                public_id,
            )
        )

        if not job:
            raise NotFoundException(
                "Background job not found."
            )

        if (
            user_id is not None
            and job.user_id != user_id
        ):
            raise NotFoundException(
                "Background job not found."
            )

        return job

    def get_response(
        self,
        db: Session,
        *,
        job_id: int,
        user_id: int | None = None,
    ) -> BackgroundJobResponse:
        return self._job_response(
            self.get_job(
                db,
                job_id=job_id,
                user_id=user_id,
            )
        )

    def get_detail(
        self,
        db: Session,
        *,
        job_id: int,
        user_id: int | None = None,
    ) -> BackgroundJobDetailResponse:
        job = self.get_job(
            db,
            job_id=job_id,
            user_id=user_id,
        )

        attempts = (
            background_job_attempt_repository
            .list_by_job_id(
                db,
                background_job_id=job.id,
            )
        )

        dependencies = (
            background_job_dependency_repository
            .list_by_job_id(
                db,
                background_job_id=job.id,
            )
        )

        dependents = (
            background_job_dependency_repository
            .list_dependents(
                db,
                depends_on_job_id=job.id,
            )
        )

        return BackgroundJobDetailResponse(
            job=self._job_response(job),
            attempts=[
                self._attempt_response(item)
                for item in attempts
            ],
            dependencies=[
                self._dependency_response(item)
                for item in dependencies
            ],
            dependents=[
                self._dependency_response(item)
                for item in dependents
            ],
        )

    def list_jobs(
        self,
        db: Session,
        *,
        user_id: int | None = None,
        queue_name: str | None = None,
        job_type: str | None = None,
        status: str | None = None,
        execution_mode: str | None = None,
        search: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> BackgroundJobListResponse:
        jobs = background_job_repository.list_filtered(
            db,
            user_id=user_id,
            queue_name=queue_name,
            job_type=job_type,
            status=status,
            execution_mode=execution_mode,
            search=search,
            skip=skip,
            limit=limit,
        )

        total = background_job_repository.count_filtered(
            db,
            user_id=user_id,
            queue_name=queue_name,
            job_type=job_type,
            status=status,
            execution_mode=execution_mode,
            search=search,
        )

        return BackgroundJobListResponse(
            items=[
                self._job_response(job)
                for job in jobs
            ],
            total=total,
            skip=skip,
            limit=limit,
        )

    def _validate_dependency_exists(
        self,
        db: Session,
        *,
        depends_on_job_id: int,
        owner_user_id: int | None,
    ) -> BackgroundJob:
        dependency_job = (
            background_job_repository.get_by_id(
                db,
                depends_on_job_id,
            )
        )

        if not dependency_job:
            raise NotFoundException(
                f"Dependency job {depends_on_job_id} "
                "was not found."
            )

        if (
            owner_user_id is not None
            and dependency_job.user_id
            != owner_user_id
        ):
            raise ConflictException(
                "A user job cannot depend on a job "
                "owned by another user."
            )

        return dependency_job

    def _job_depends_on(
        self,
        db: Session,
        *,
        job_id: int,
        possible_ancestor_id: int,
        visited: set[int] | None = None,
    ) -> bool:
        if job_id == possible_ancestor_id:
            return True

        checked = visited or set()

        if job_id in checked:
            return False

        checked.add(job_id)

        dependencies = (
            background_job_dependency_repository
            .list_by_job_id(
                db,
                background_job_id=job_id,
            )
        )

        for dependency in dependencies:
            if (
                dependency.depends_on_job_id
                == possible_ancestor_id
            ):
                return True

            if self._job_depends_on(
                db,
                job_id=dependency.depends_on_job_id,
                possible_ancestor_id=possible_ancestor_id,
                visited=checked,
            ):
                return True

        return False

    def _create_dependencies(
        self,
        db: Session,
        *,
        job: BackgroundJob,
        dependencies,
    ) -> None:
        for dependency_data in dependencies:
            dependency_job = (
                self._validate_dependency_exists(
                    db,
                    depends_on_job_id=(
                        dependency_data
                        .depends_on_job_id
                    ),
                    owner_user_id=job.user_id,
                )
            )

            if dependency_job.id == job.id:
                raise ConflictException(
                    "A job cannot depend on itself."
                )

            if self._job_depends_on(
                db,
                job_id=dependency_job.id,
                possible_ancestor_id=job.id,
            ):
                raise ConflictException(
                    "Circular job dependency detected."
                )

            dependency = BackgroundJobDependency(
                background_job_id=job.id,
                depends_on_job_id=dependency_job.id,
                dependency_type=(
                    dependency_data
                    .dependency_type.value
                ),
            )

            db.add(dependency)

    def create_job(
        self,
        db: Session,
        *,
        data: BackgroundJobCreate,
    ) -> tuple[BackgroundJobResponse, bool]:
        if data.idempotency_key:
            existing = (
                background_job_repository
                .get_by_idempotency_key(
                    db,
                    data.idempotency_key,
                )
            )

            if existing:
                return (
                    self._job_response(existing),
                    False,
                )

        now = utc_now()

        is_scheduled = (
            data.scheduled_at is not None
            and data.scheduled_at > now
        )

        initial_status = (
            JobStatus.SCHEDULED.value
            if is_scheduled
            else JobStatus.QUEUED.value
        )

        available_at = (
            data.scheduled_at
            if is_scheduled
            else now
        )

        job = BackgroundJob(
            public_id=uuid4().hex,
            job_type=data.job_type,
            queue_name=data.queue_name.value,
            execution_mode=data.execution_mode.value,
            status=initial_status,
            priority=data.priority.value,
            user_id=data.user_id,
            tryon_job_id=data.tryon_job_id,
            external_ai_job_id=(
                data.external_ai_job_id
            ),
            idempotency_key=data.idempotency_key,
            payload_json=self._serialize_json(
                data.payload
            ),
            result_json=None,
            metadata_json=self._serialize_json(
                data.metadata
            ),
            progress=0.0,
            attempt_count=0,
            max_attempts=data.max_attempts,
            retry_backoff_seconds=(
                data.retry_backoff_seconds
            ),
            retry_backoff_multiplier=(
                data.retry_backoff_multiplier
            ),
            timeout_seconds=data.timeout_seconds,
            scheduled_at=data.scheduled_at,
            available_at=available_at,
            queued_at=(
                None
                if is_scheduled
                else now
            ),
            is_cancelable=data.is_cancelable,
            retain_until=data.retain_until,
        )

        try:
            db.add(job)
            db.flush()

            self._create_dependencies(
                db,
                job=job,
                dependencies=data.dependencies,
            )

            db.commit()
            db.refresh(job)

            return self._job_response(job), True

        except Exception:
            db.rollback()
            raise

    def create_user_job(
        self,
        db: Session,
        *,
        user_id: int,
        data: UserBackgroundJobCreate,
    ) -> tuple[BackgroundJobResponse, bool]:
        internal_data = BackgroundJobCreate(
            job_type=data.job_type,
            queue_name=data.queue_name,
            execution_mode=data.execution_mode,
            priority=data.priority,
            user_id=user_id,
            tryon_job_id=data.tryon_job_id,
            external_ai_job_id=None,
            idempotency_key=data.idempotency_key,
            payload=data.payload,
            metadata=data.metadata,
            dependencies=data.dependencies,
            max_attempts=data.max_attempts,
            retry_backoff_seconds=(
                data.retry_backoff_seconds
            ),
            retry_backoff_multiplier=(
                data.retry_backoff_multiplier
            ),
            timeout_seconds=data.timeout_seconds,
            scheduled_at=data.scheduled_at,
            is_cancelable=data.is_cancelable,
            retain_until=None,
        )

        return self.create_job(
            db,
            data=internal_data,
        )

    def request_cancellation(
        self,
        db: Session,
        *,
        job_id: int,
        reason: str | None = None,
        user_id: int | None = None,
    ) -> BackgroundJobCancelResponse:
        job = background_job_repository.get_for_update(
            db,
            job_id,
        )

        if not job:
            raise NotFoundException(
                "Background job not found."
            )

        if (
            user_id is not None
            and job.user_id != user_id
        ):
            db.rollback()

            raise NotFoundException(
                "Background job not found."
            )

        if not job.is_cancelable:
            db.rollback()

            raise ConflictException(
                "This job cannot be canceled."
            )

        if job.status in self.TERMINAL_STATUSES:
            db.rollback()

            return BackgroundJobCancelResponse(
                job=self._job_response(job),
                cancellation_requested=False,
                canceled_immediately=False,
                message=(
                    "Job already has a terminal status."
                ),
            )

        now = utc_now()

        metadata = self._parse_json(
            job.metadata_json
        )

        if reason:
            metadata["cancellation_reason"] = reason

        if (
            job.status
            in self.IMMEDIATELY_CANCELABLE_STATUSES
        ):
            job.status = JobStatus.CANCELED.value
            job.canceled_at = now
            job.completed_at = now
            job.progress_message = (
                "Job canceled before execution."
            )
            job.lease_owner = None
            job.lease_token = None
            job.lease_expires_at = None
            job.metadata_json = self._serialize_json(
                metadata
            )

            db.add(job)
            db.commit()
            db.refresh(job)

            return BackgroundJobCancelResponse(
                job=self._job_response(job),
                cancellation_requested=True,
                canceled_immediately=True,
                message=(
                    "Job canceled before execution."
                ),
            )

        job.status = (
            JobStatus.CANCEL_REQUESTED.value
        )
        job.cancel_requested_at = now
        job.metadata_json = self._serialize_json(
            metadata
        )

        db.add(job)
        db.commit()
        db.refresh(job)

        return BackgroundJobCancelResponse(
            job=self._job_response(job),
            cancellation_requested=True,
            canceled_immediately=False,
            message=(
                "Cancellation was requested. "
                "The worker will stop the job safely."
            ),
        )

    def retry_job(
        self,
        db: Session,
        *,
        job_id: int,
        data: BackgroundJobRetryRequest,
    ) -> BackgroundJobRetryResponse:
        job = background_job_repository.get_for_update(
            db,
            job_id,
        )

        if not job:
            raise NotFoundException(
                "Background job not found."
            )

        if job.status not in self.RETRYABLE_STATUSES:
            db.rollback()

            raise ConflictException(
                "Job cannot be retried in its current state."
            )

        if (
            not data.reset_attempt_count
            and job.attempt_count >= job.max_attempts
        ):
            db.rollback()

            raise ConflictException(
                "Job has exhausted its configured attempts. "
                "Use reset_attempt_count to retry it manually."
            )

        now = utc_now()

        is_scheduled = (
            data.scheduled_at is not None
            and data.scheduled_at > now
        )

        job.status = (
            JobStatus.SCHEDULED.value
            if is_scheduled
            else JobStatus.QUEUED.value
        )

        job.scheduled_at = data.scheduled_at
        job.available_at = (
            data.scheduled_at
            if is_scheduled
            else now
        )

        job.queued_at = (
            None
            if is_scheduled
            else now
        )

        if data.priority is not None:
            job.priority = data.priority.value

        if data.reset_attempt_count:
            job.attempt_count = 0

        job.progress = 0.0
        job.progress_message = (
            "Job queued for manual retry."
        )

        job.error_code = None
        job.error_message = None
        job.error_details_json = None
        job.result_json = None

        job.completed_at = None
        job.canceled_at = None
        job.cancel_requested_at = None
        job.claimed_at = None
        job.started_at = None
        job.last_heartbeat_at = None

        job.lease_owner = None
        job.lease_token = None
        job.lease_expires_at = None
        job.worker_name = None
        job.worker_version = None
        job.provider_job_id = None

        metadata = self._parse_json(
            job.metadata_json
        )

        metadata["manual_retry_at"] = now.isoformat()

        if data.reason:
            metadata["manual_retry_reason"] = (
                data.reason
            )

        job.metadata_json = self._serialize_json(
            metadata
        )

        db.add(job)
        db.commit()
        db.refresh(job)

        return BackgroundJobRetryResponse(
            job=self._job_response(job),
            retried=True,
            message="Job queued for retry.",
        )

    def update_progress(
        self,
        db: Session,
        *,
        job_id: int,
        data: BackgroundJobProgressUpdate,
    ) -> BackgroundJobResponse:
        job = background_job_repository.get_for_update(
            db,
            job_id,
        )

        if not job:
            raise NotFoundException(
                "Background job not found."
            )

        if job.status not in {
            JobStatus.CLAIMED.value,
            JobStatus.RUNNING.value,
            JobStatus.CANCEL_REQUESTED.value,
        }:
            db.rollback()

            raise ConflictException(
                "Progress cannot be updated for "
                "the current job state."
            )

        job.progress = data.progress
        job.progress_message = data.message
        job.last_heartbeat_at = utc_now()

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

        return self._job_response(job)

    def list_attempts(
        self,
        db: Session,
        *,
        job_id: int,
        user_id: int | None = None,
    ) -> BackgroundJobAttemptListResponse:
        job = self.get_job(
            db,
            job_id=job_id,
            user_id=user_id,
        )

        attempts = (
            background_job_attempt_repository
            .list_by_job_id(
                db,
                background_job_id=job.id,
            )
        )

        return BackgroundJobAttemptListResponse(
            items=[
                self._attempt_response(item)
                for item in attempts
            ],
            total=len(attempts),
        )

    def list_dependencies(
        self,
        db: Session,
        *,
        job_id: int,
        user_id: int | None = None,
    ) -> BackgroundJobDependencyListResponse:
        job = self.get_job(
            db,
            job_id=job_id,
            user_id=user_id,
        )

        dependencies = (
            background_job_dependency_repository
            .list_by_job_id(
                db,
                background_job_id=job.id,
            )
        )

        return BackgroundJobDependencyListResponse(
            items=[
                self._dependency_response(item)
                for item in dependencies
            ],
            total=len(dependencies),
        )


background_job_service = BackgroundJobService()