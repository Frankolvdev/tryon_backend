from sqlalchemy.orm import Session

from app.common.enums import ScheduledJobRunStatus
from app.common.exceptions import ConflictException, NotFoundException
from app.common.time import utc_now
from app.models.scheduled_job import ScheduledJob
from app.models.scheduled_job_run import ScheduledJobRun
from app.repositories.scheduled_job_repository import scheduled_job_repository
from app.repositories.scheduled_job_run_repository import scheduled_job_run_repository
from app.schemas.scheduler import ScheduledJobCreate, ScheduledJobUpdate


class SchedulerService:
    def list_jobs(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ScheduledJob]:
        return scheduled_job_repository.list_all(db, skip=skip, limit=limit)

    def create_job(self, db: Session, data: ScheduledJobCreate) -> ScheduledJob:
        existing = scheduled_job_repository.get_by_key(db, data.key)

        if existing:
            raise ConflictException("Scheduled job key already exists.")

        return scheduled_job_repository.create(db, data=data.model_dump())

    def update_job(
        self,
        db: Session,
        job_id: int,
        data: ScheduledJobUpdate,
    ) -> ScheduledJob:
        job = scheduled_job_repository.get_by_id(db, job_id)

        if not job:
            raise NotFoundException("Scheduled job not found.")

        return scheduled_job_repository.update(
            db,
            db_obj=job,
            data=data.model_dump(exclude_unset=True),
        )

    def list_runs(
        self,
        db: Session,
        *,
        job_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ScheduledJobRun]:
        return scheduled_job_run_repository.list_by_job_id(
            db,
            job_id,
            skip=skip,
            limit=limit,
        )

    def run_job_manually(
        self,
        db: Session,
        *,
        job_id: int,
        note: str | None = None,
    ) -> ScheduledJobRun:
        job = scheduled_job_repository.get_by_id(db, job_id)

        if not job:
            raise NotFoundException("Scheduled job not found.")

        run = ScheduledJobRun(
            scheduled_job_id=job.id,
            status=ScheduledJobRunStatus.RUNNING.value,
            started_at=utc_now(),
            output=note,
        )

        db.add(run)
        db.commit()
        db.refresh(run)

        try:
            output = self._execute_registered_job(db=db, job_key=job.key, note=note)

            run.status = ScheduledJobRunStatus.SUCCESS.value
            run.finished_at = utc_now()
            run.output = output

            job.last_run_at = run.finished_at

        except Exception as error:
            run.status = ScheduledJobRunStatus.FAILED.value
            run.finished_at = utc_now()
            run.error_message = str(error)

        db.add(run)
        db.add(job)
        db.commit()
        db.refresh(run)

        return run

    def _execute_registered_job(
        self,
        db: Session,
        *,
        job_key: str,
        note: str | None = None,
    ) -> str:
        if job_key in ["process_pending_webhooks", "retry_failed_webhooks"]:
            from app.services.webhook_service import webhook_service

            result = webhook_service.process_pending_events(db)
            return f"Webhook job completed: {result}"

        if job_key == "poll_pending_runpod_jobs":
            from app.services.external_ai_job_service import external_ai_job_service

            result = external_ai_job_service.poll_pending_runpod_jobs(db)
            return f"RunPod polling completed: {result}"

        return f"Manual run completed. {note or ''}".strip()


scheduler_service = SchedulerService()